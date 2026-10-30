"""Plan format, template questions -> plans (no AI), and plan validation.

A plan is plain JSON:
  {"sheet_id", "operation": total|top_n|group_by|compare_periods|low_stock|filter,
   "metric": inventory_value|retail_value|revenue|quantity|count|amount|sum:<column>,
   "group_field": <column>, "n": 1-20, "filters": [{"field","op","value"}],
   "period": {"unit": month|quarter|year}}
Every field name is checked against the sheet's profile before anything runs.
"""
import datetime as dt
import re

OPS = {"total", "top_n", "group_by", "compare_periods", "low_stock", "filter"}
NEEDS_METRIC = {"total", "top_n", "group_by", "compare_periods"}
FILTER_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "contains"}
UNITS = {"month", "quarter", "year"}
NUMERIC = {"integer", "float"}
FRIENDLY = {"quantity": "quantity or stock", "unit_cost": "unit cost", "price": "price",
            "reorder_level": "reorder level", "date": "date", "product": "product name",
            "sku": "SKU", "category": "category"}
AMOUNT_WORDS = ["amount", "total", "expense", "spend", "cost", "value", "revenue", "sales"]


class PlanError(ValueError):
    """A problem the user can read (shown as-is)."""


def q(name: str) -> str:
    """Quote a column name for SQL. Only ever called with names found in the profile."""
    return '"' + str(name).replace('"', '""') + '"'


def num(col: str) -> str:
    return f"CAST({q(col)} AS DOUBLE)"


def columns(profile) -> dict:
    return {c["name"]: c for c in profile.get("columns", [])}


def find_amount_column(profile):
    cols = [c for c in profile.get("columns", []) if c["type"] in NUMERIC]
    for w in AMOUNT_WORDS:
        for c in cols:
            if w in re.findall(r"[a-z]+", c["name"].lower()):
                return c["name"]
    return None


def no_field(f):
    return PlanError(f"I can't answer that because the sheet has no {FRIENDLY.get(f, f)} column.")


def default_metric(profile):
    m = profile.get("mapped_fields", {})
    if "reorder_level" in m and "unit_cost" in m and "quantity" in m:
        return "inventory_value"
    if "quantity" in m and "price" in m:
        return "revenue"
    if "quantity" in m and "unit_cost" in m:
        return "inventory_value"
    if find_amount_column(profile):
        return "amount"
    if "price" in m:
        return "revenue"
    return "quantity" if "quantity" in m else "count"


def resolve_metric(metric, profile):
    """-> (sql_expr, label, format, step_text). Raises PlanError if the sheet can't support it."""
    m = profile.get("mapped_fields", {})

    def need(*fs):
        for f in fs:
            if f not in m:
                raise no_field(f)

    if metric == "inventory_value":
        need("quantity", "unit_cost")
        return (f"SUM({num(m['quantity'])} * {num(m['unit_cost'])})", "Inventory value", "currency",
                f"Inventory value = sum of {m['quantity']} x {m['unit_cost']}")
    if metric == "retail_value":
        need("quantity", "price")
        return (f"SUM({num(m['quantity'])} * {num(m['price'])})", "Retail value", "currency",
                f"Retail value = sum of {m['quantity']} x {m['price']}")
    if metric == "revenue":
        if "quantity" in m and "price" in m:
            return (f"SUM({num(m['quantity'])} * {num(m['price'])})", "Revenue", "currency",
                    f"Revenue = sum of {m['quantity']} x {m['price']}")
        amt = find_amount_column(profile)
        if amt:
            return (f"SUM({num(amt)})", "Revenue", "currency", f"Revenue = sum of the {amt} column")
        if "price" in m:
            return (f"SUM({num(m['price'])})", "Revenue", "currency",
                    f"Revenue = sum of the {m['price']} column (the sheet has no quantity column)")
        raise PlanError("I can't answer that because the sheet has no price or amount column.")
    if metric == "quantity":
        need("quantity")
        return (f"SUM({num(m['quantity'])})", "Total quantity", "number", f"Total quantity = sum of {m['quantity']}")
    if metric == "count":
        return ("COUNT(*)", "Number of rows", "number", "Counted the rows")
    if metric == "amount":
        amt = find_amount_column(profile)
        if not amt:
            raise PlanError("I can't answer that because the sheet has no amount, total or cost column.")
        return (f"SUM({num(amt)})", amt.replace("_", " ").capitalize(), "currency", f"Summed the {amt} column")
    if isinstance(metric, str) and metric.startswith("sum:"):
        col = metric[4:]
        c = columns(profile).get(col)
        if not c or c["type"] not in NUMERIC:
            raise PlanError(f"I can't answer that because the sheet has no number column called '{col}'.")
        return (f"SUM({num(col)})", col.replace("_", " ").capitalize(), "number", f"Summed the {col} column")
    raise PlanError("I couldn't work out what to measure for that question.")


def date_column(profile):
    d = profile.get("mapped_fields", {}).get("date")
    if d:
        return d
    for c in profile.get("columns", []):
        if c["type"] == "date":
            return c["name"]
    return None


def label_column(profile):
    m = profile.get("mapped_fields", {})
    return m.get("product") or m.get("sku")


def validate_plan(plan, profile):
    """Return a cleaned plan or raise PlanError. Used for AI plans and template plans alike."""
    if not isinstance(plan, dict):
        raise PlanError("I couldn't work out how to answer that.")
    op = plan.get("operation")
    if op not in OPS:
        raise PlanError("I couldn't work out how to answer that.")
    cols = columns(profile)
    m = profile.get("mapped_fields", {})
    out = {"sheet_id": plan.get("sheet_id"), "operation": op, "filters": []}

    if op in NEEDS_METRIC:
        out["metric"] = plan.get("metric") or default_metric(profile)
        resolve_metric(out["metric"], profile)
    if op in ("top_n", "group_by"):
        gf = plan.get("group_field") or m.get("product") or m.get("sku") or m.get("category")
        if gf not in cols:
            raise PlanError("I can't answer that because I couldn't find which column to group by.")
        out["group_field"] = gf
        try:
            out["n"] = max(1, min(20, int(plan.get("n") or 5)))
        except (TypeError, ValueError):
            out["n"] = 5
    if op == "compare_periods":
        if not date_column(profile):
            raise no_field("date")
        unit = (plan.get("period") or {}).get("unit", "month")
        out["period"] = {"unit": unit if unit in UNITS else "month"}
    if op == "low_stock":
        for f in ("quantity", "reorder_level"):
            if f not in m:
                raise no_field(f)

    for f in (plan.get("filters") or [])[:5]:
        if not isinstance(f, dict) or f.get("field") not in cols or f.get("op") not in FILTER_OPS:
            raise PlanError("I couldn't match part of your question to a column in the sheet.")
        v = f.get("value")
        if isinstance(v, (dict, list)) or v is None:
            raise PlanError("I couldn't understand a value in your question.")
        out["filters"].append({"field": f["field"], "op": f["op"], "value": v})
    return out


# ------------------------------------------------------------------ template questions (no AI)
def is_projection(question: str) -> bool:
    return bool(re.search(r"\b(project|projection|projections|forecast|predict|prediction|estimate the rest|"
                          r"end of (the |this |our )?(fiscal )?year|next (year|quarter|month)|will (we|sales|revenue))\b",
                          question.lower()))


def _metric_from_words(q_):
    if re.search(r"inventory value|stock value|value of (our |the |my )?(stock|inventory)|worth", q_):
        return "inventory_value"
    if "retail value" in q_:
        return "retail_value"
    if re.search(r"revenue|sales|sold|income|turnover|earn", q_):
        return "revenue"
    if re.search(r"expense|spend|spent|\bcosts?\b|\bbills?\b", q_):
        return "amount"
    if re.search(r"quantity|units|stock level|in stock", q_):
        return "quantity"
    if re.search(r"how many (products|items|skus|rows|orders|transactions)|number of|count", q_):
        return "count"
    return None


def _month_start(d):
    return d.replace(day=1)


def _relative_range(q_, today):
    """'last month', 'this year'... -> (label, start, end_exclusive) or None."""
    def add_months(d, n):
        i = d.year * 12 + d.month - 1 + n
        return dt.date(i // 12, i % 12 + 1, 1)

    ms = _month_start(today)
    if "last month" in q_:
        return "last month", add_months(ms, -1), ms
    if "this month" in q_:
        return "this month", ms, add_months(ms, 1)
    qs = dt.date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
    if "last quarter" in q_:
        return "last quarter", add_months(qs, -3), qs
    if "this quarter" in q_:
        return "this quarter", qs, add_months(qs, 3)
    if "last year" in q_:
        return "last year", dt.date(today.year - 1, 1, 1), dt.date(today.year, 1, 1)
    if "this year" in q_:
        return "this year", dt.date(today.year, 1, 1), dt.date(today.year + 1, 1, 1)
    return None


def _group_field_from_question(q_, profile):
    mt = re.search(r"\b(?:by|per|for each|each)\s+([a-z_]+)(?:\s+([a-z_]+))?", q_)
    if not mt:
        return None
    for cand in [w for w in mt.groups() if w]:
        c = cand[:-1] if cand.endswith("s") and len(cand) > 3 else cand
        for col in profile.get("columns", []):
            if c in re.findall(r"[a-z]+", col["name"].lower()) and col["type"] not in NUMERIC | {"date"}:
                return col["name"]
        if c in ("category", "type", "group") and profile.get("mapped_fields", {}).get("category"):
            return profile["mapped_fields"]["category"]
    return None


def template_plan(question, sheet_id, profile, today=None):
    """Turn a common question into a plan without AI. Returns a plan or None (then the AI is asked)."""
    today = today or dt.date.today()
    q_ = " ".join(re.findall(r"[a-z0-9_]+", question.lower().replace("-", " ")))
    # If the question talks about a column the rules don't understand (e.g. "payment method", "branch"),
    # hand it to the AI instead of guessing and silently answering a different question.
    words = set(q_.split())
    for c in profile.get("columns", []):
        if c.get("mapped_to") is None and c["type"] == "text" and c.get("distinct", 999) <= 50:
            if any(w in words for w in re.findall(r"[a-z]+", c["name"].lower()) if w not in {"id", "no", "name", "number", "code", "the"}):
                return None
    metric = _metric_from_words(q_)
    plan = {"sheet_id": sheet_id}

    if re.search(r"low (in )?stock|running low|run(ning)? out|out of stock|stock ?out|reorder|restock|below (the )?(reorder|threshold|minimum)", q_):
        plan["operation"] = "low_stock"
    elif re.search(r"\b(compare|compared|versus|vs|change|changed|grew|grow|growth|increase|increased|decrease|decreased|trend|up|down)\b", q_) \
            and re.search(r"\b(month|quarter|year|last|previous|prior)\b", q_):
        plan["operation"] = "compare_periods"
        plan["period"] = {"unit": "quarter" if "quarter" in q_ else "year" if re.search(r"\byear\b", q_) else "month"}
    elif re.search(r"\b(top|best|highest|most|biggest|largest|leading|bestselling|best selling)\b", q_):
        plan["operation"] = "top_n"
        mt = re.search(r"\btop (\d+)\b|\b(\d+) (?:best|top)\b", q_)
        words = {"three": 3, "five": 5, "ten": 10}
        mw = re.search(r"\btop (three|five|ten)\b", q_)
        plan["n"] = int(next(g for g in mt.groups() if g)) if mt else words[mw.group(1)] if mw else 5
        plan["group_field"] = _group_field_from_question(q_, profile)
    elif re.search(r"\b(by|per|for each|breakdown|broken down)\b", q_):
        gf = _group_field_from_question(q_, profile)
        if not gf:
            return None
        plan["operation"] = "group_by"
        plan["group_field"] = gf
    elif re.search(r"\b(total|how much|sum|overall|what is our|what s our|how many|worth|value)\b", q_):
        plan["operation"] = "total"
    else:
        return None

    if metric:
        plan["metric"] = metric
    rel = _relative_range(q_, today)
    if rel and plan["operation"] in ("total", "top_n", "group_by"):
        d = date_column(profile)
        if not d:
            raise PlanError(f"I can't limit this to {rel[0]} because the sheet has no date column.")
        plan["filters"] = [{"field": d, "op": "gte", "value": rel[1].isoformat()},
                           {"field": d, "op": "lt", "value": rel[2].isoformat()}]
    return validate_plan(plan, profile)


def followups(profile):
    m = profile.get("mapped_fields", {})
    out = []
    if "date" in m:
        out.append("How did it change compared to last month?")
    if "product" in m or "sku" in m:
        out.append("What are the top 5 products?")
    if "reorder_level" in m and "quantity" in m:
        out.append("Which products are running low in stock?")
    return out[:3]
