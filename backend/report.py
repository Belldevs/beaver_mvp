"""Multi-step analysis ("report") mode.

Flow: detect a report-style question -> code runs several safe calculations (trend, drivers, share,
ranking, stock) -> every number is pre-formatted here -> the AI only writes the words (or the rules
fallback does) -> numbers in the text are checked against the verified facts.
The AI never sees rows and never does maths.

Colors: green = positive trend, red = negative, orange = something to watch.
"""
import datetime as dt
import io
import logging
import re
import threading

import pandas as pd

import ai
from plans import PlanError, date_column, default_metric, label_column, num, q, resolve_metric
from runner import _period_label, _r, _run

log = logging.getLogger("beaver.report")

GREEN, RED, ORANGE, NEUTRAL = "#16A34A", "#DC2626", "#F97316", "#9CA3AF"
GREYS = ["#111827", "#374151", "#6B7280", "#9CA3AF", "#D1D5DB", "#E5E7EB", "#F3F4F6"]
UP_PCT, DOWN_PCT, CONCENTRATION = 2.0, -5.0, 40.0  # >=+2% green, <=-5% red, otherwise orange; one slice >40% = watch
TONE_COLOR = {"positive": GREEN, "negative": RED, "watch": ORANGE, "neutral": NEUTRAL}
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                          "august", "september", "october", "november", "december"])}
SYMBOLS = {"USD": "$", "NGN": "₦", "GBP": "£", "EUR": "€", "GHS": "GH₵", "KES": "KSh ", "ZAR": "R"}

REPORT_RE = re.compile(
    r"\b(overview|summary|summari[sz]e|report|analy[sz]e|analysis|insights?|performance|full picture|big picture|"
    r"trend|trends|trending|what happened|how is the business|how are we doing)\b"
    r"|\bhow (did|is|are|was|were) (the |our |my )?(business|company|shop|store|we|sales|revenue|things|month)\b"
    r"|\bwhy\b.*\b(drop|dropped|fall|fell|down|decline|declined|dip|dipped|increase|increased|rise|rose|change|changed|low|lower|high|higher)\b")


def is_report_question(question: str) -> bool:
    return bool(REPORT_RE.search(question.lower()))


# ------------------------------------------------------------------ formatting (all numbers are formatted here)
def money(v, fmt, currency):
    if v is None:
        return "n/a"
    sign = "-" if v < 0 else ""
    v = abs(v)
    s = f"{v:,.0f}" if v >= 100 else f"{v:,.2f}"
    if fmt == "currency":
        sym = SYMBOLS.get(currency, f"{currency} ")
        return f"{sign}{sym}{s}"
    return f"{sign}{s}"


def pct_s(p):
    return "n/a" if p is None else f"{p:+.1f}%"


def tone_for(pct, partial=False):
    if pct is None:
        return "watch"
    if pct >= UP_PCT:
        return "positive"
    if pct <= DOWN_PCT and not partial:
        return "negative"
    return "watch"


def _month_add(d, n):
    i = d.year * 12 + d.month - 1 + n
    return pd.Timestamp(i // 12, i % 12 + 1, 1)


def _target_months(question, available, today):
    """Pick the month being analysed. Returns (target, prev, note). Defaults to the latest month in the data."""
    q_ = question.lower()
    latest = max(available)
    found = []
    for name, num_ in MONTHS.items():
        if re.search(rf"\b{name}\b", q_):
            cands = [p for p in available if p.month == num_]
            if cands:
                found.append(max(cands))
    if "last month" in q_ and not found:
        lm = _month_add(today.replace(day=1), -1)
        if lm in available:
            found.append(lm)
    if len(found) >= 2:
        found = sorted(set(found))
        return found[-1], found[-2], None
    if found:
        return found[0], _month_add(found[0], -1), None
    return latest, _month_add(latest, -1), None


# ------------------------------------------------------------------ sections
def _per_point_colors(values):
    out = [NEUTRAL]
    for a, b in zip(values, values[1:]):
        p = None if not a else (b - a) / abs(a) * 100
        out.append(GREEN if p is not None and p >= UP_PCT else RED if p is not None and p <= DOWN_PCT else ORANGE)
    return out


def _group_rows(con, g, expr, d, cur, prev):
    """-> [(name, cur_value, prev_value)] in ONE query using FILTER, so the maths stays in SQL."""
    if d and cur is not None:
        c = f"date_trunc('month', CAST({q(d)} AS TIMESTAMP)) = CAST(? AS TIMESTAMP)"
        rows, _ = _run(con, f"SELECT {q(g)}, {expr} FILTER (WHERE {c}), {expr} FILTER (WHERE {c}) FROM t "
                            f"WHERE {q(d)} IS NOT NULL GROUP BY 1", [cur.isoformat(), prev.isoformat()])
    else:
        rows, _ = _run(con, f"SELECT {q(g)}, {expr}, NULL FROM t GROUP BY 1", [])
    return [("(blank)" if k is None else str(k), float(c_ or 0), None if p_ is None and not d else float(p_ or 0))
            for k, c_, p_ in rows]


def run_report(profile, parquet_bytes, sheet_name, question, currency="USD", today=None):
    import duckdb
    today = today or dt.date.today()
    df = pd.read_parquet(io.BytesIO(parquet_bytes))
    if len(df) > 500_000:
        raise PlanError("This sheet is too large to analyse.")
    con = duckdb.connect(":memory:")
    timer = threading.Timer(25, con.interrupt)
    timer.start()
    try:
        con.register("t", df)
        return _build(con, profile, sheet_name, question, currency, today)
    finally:
        timer.cancel()
        con.close()


def _build(con, profile, sheet_name, question, currency, today):
    m = profile.get("mapped_fields", {})
    metric = default_metric(profile)
    expr, label, fmt, mstep = resolve_metric(metric, profile)
    d = date_column(profile)
    steps = [f"Used the sheet '{sheet_name}'", mstep]
    sections, facts = [], {}
    F = lambda v: money(v, fmt, currency)  # noqa: E731

    # ---- trend (all periods) ------------------------------------------------
    target = prev = None
    chg = None
    partial = False
    note = None
    if d:
        rows, _ = _run(con, f"SELECT date_trunc('month', CAST({q(d)} AS TIMESTAMP)) AS p, {expr} FROM t "
                            f"WHERE {q(d)} IS NOT NULL GROUP BY 1 ORDER BY 1", [])
        by = {pd.Timestamp(p): float(v or 0) for p, v in rows}
        if len(by) >= 2:
            target, prev, note = _target_months(question, set(by), today)
            first = max(min(by), _month_add(target, -11))
            periods = []
            p = first
            while p <= target:
                periods.append(p)
                p = _month_add(p, 1)
            vals = [_r(by.get(p, 0.0)) for p in periods]
            cur_v, prev_v = by.get(target, 0.0), by.get(prev, 0.0)
            amount = cur_v - prev_v
            pct = round(amount / abs(prev_v) * 100, 1) if prev_v else None
            mx, _ = _run(con, f"SELECT MAX(CAST({q(d)} AS DATE)) FROM t", [])
            last_day = pd.Timestamp(mx[0][0])
            partial = target == max(by) and last_day < (_month_add(target, 1) - pd.Timedelta(days=1))
            tone = tone_for(pct, partial)
            chg = {"pct": pct, "amount": _r(amount), "direction": "up" if amount > 0 else "down" if amount < 0 else "flat",
                   "vs": _period_label(prev, "month"), "previous": _r(prev_v), "format": fmt}
            best = max(periods, key=lambda x: by.get(x, 0.0))
            worst = min(periods, key=lambda x: by.get(x, 0.0))
            sections.append({"id": "trend", "title": f"{label} trend", "tone": tone, "color": TONE_COLOR[tone],
                             "chart": {"type": "line", "labels": [_period_label(p, "month") for p in periods], "values": vals,
                                       "colors": _per_point_colors(vals), "color": TONE_COLOR[tone], "format": fmt,
                                       "highlight": len(periods) - 1}})
            facts["trend"] = {"month": _period_label(target, "month"), "value": F(cur_v), "previous_month": _period_label(prev, "month"),
                              "previous_value": F(prev_v), "change": F(amount), "change_pct": pct_s(pct),
                              "best_month": f"{_period_label(best, 'month')} ({F(by.get(best, 0.0))})",
                              "weakest_month": f"{_period_label(worst, 'month')} ({F(by.get(worst, 0.0))})",
                              "months_covered": str(len(periods)),
                              "data_note": (f"{_period_label(target, 'month')} is incomplete: data only runs to {last_day:%d %b %Y}"
                                            if partial else "")}
            steps.append(f"Totalled {label.lower()} for each of the last {len(periods)} months")
            steps.append(f"Compared {_period_label(target, 'month')} with {_period_label(prev, 'month')}")
        else:
            steps.append("Only one month of dates in this sheet, so there is no trend to chart")

    # ---- grouped sections: drivers, share, ranking ----------------------------
    gcat = m.get("category")
    gprod = label_column(profile)
    primary = gcat or gprod
    secondary = gprod if gcat and gprod and gprod != gcat else None
    cur_p, prev_p = (target, prev) if target is not None else (None, None)

    groups = {}
    for key, g in (("primary", primary), ("secondary", secondary)):
        if g:
            groups[key] = (g, _group_rows(con, g, expr, d if target is not None else None, cur_p, prev_p))

    if "primary" in groups:
        g, rows = groups["primary"]
        gname = g.replace("_", " ")
        rows = [r for r in rows if r[1] or (r[2] or 0)]
        if target is not None and chg and rows:
            deltas = sorted(((n, c_ - (p_ or 0)) for n, c_, p_ in rows), key=lambda x: x[1])
            losers = [x for x in deltas if x[1] < 0][:3]
            gainers = [x for x in reversed(deltas) if x[1] > 0][:3]
            picks = losers + gainers[::-1]
            if picks:
                pm = {n: p_ or 0 for n, c_, p_ in rows}
                dtone = "negative" if chg["direction"] == "down" and losers else "positive" if chg["direction"] == "up" else "watch"
                sections.append({"id": "drivers", "title": f"What moved {label.lower()} by {gname}", "tone": dtone, "color": TONE_COLOR[dtone],
                                 "chart": {"type": "bar", "labels": [n for n, _ in picks], "values": [_r(v) for _, v in picks],
                                           "colors": [RED if v < 0 else GREEN for _, v in picks], "color": TONE_COLOR[dtone], "format": fmt},
                                 "table": {"columns": [{"key": "name", "label": gname.capitalize()}, {"key": "change", "label": "Change", "format": fmt},
                                                       {"key": "pct", "label": "% change"}],
                                           "rows": [{"name": n, "change": _r(v), "pct": pct_s(round(v / pm[n] * 100, 1) if pm.get(n) else None)} for n, v in picks]}})
                facts["drivers"] = {"grouped_by": gname,
                                    "biggest_drops": [f"{n}: {F(v)}" for n, v in losers] or ["none"],
                                    "biggest_gains": [f"{n}: {F(v)}" for n, v in gainers[:3]] or ["none"],
                                    "total_change": F(chg["amount"])}
                steps.append(f"Measured each {gname}'s change between the two months")
        total = sum(r[1] for r in rows)
        if total > 0:
            top = sorted(rows, key=lambda r: -r[1])
            head, rest = top[:6], top[6:]
            items = [(n, c_) for n, c_, _ in head] + ([("Other", sum(c_ for _, c_, _ in rest))] if rest else [])
            shares = [round(v / total * 100, 1) for _, v in items]
            conc = shares[0] > CONCENTRATION if shares else False
            colors = [ORANGE if (i == 0 and conc) else GREYS[min(i, len(GREYS) - 1)] for i in range(len(items))]
            stone = "watch" if conc else "neutral"
            sections.append({"id": "share", "title": f"Share of {label.lower()} by {gname}", "tone": stone, "color": TONE_COLOR[stone],
                             "chart": {"type": "pie", "labels": [n for n, _ in items], "values": [_r(v) for _, v in items],
                                       "shares": shares, "colors": colors, "color": TONE_COLOR[stone], "format": fmt},
                             "table": {"columns": [{"key": "name", "label": gname.capitalize()}, {"key": "value", "label": label, "format": fmt},
                                                   {"key": "share", "label": "Share"}],
                                       "rows": [{"name": n, "value": _r(v), "share": f"{s:.1f}%"} for (n, v), s in zip(items, shares)]}})
            facts["share"] = {"grouped_by": gname, "period": _period_label(target, "month") if target is not None else "all rows",
                              "total": F(total), "leader": f"{items[0][0]} ({shares[0]:.1f}%)",
                              "top_three": [f"{n} ({s:.1f}%)" for (n, _), s in list(zip(items, shares))[:3]],
                              "concentration_risk": f"{items[0][0]} makes up {shares[0]:.1f}% of the total" if conc else ""}
            steps.append(f"Split the total by {gname} to see each one's share")

    rank_src = groups.get("secondary") or (groups.get("primary") if not gcat else None)
    if rank_src:
        g, rows = rank_src
        gname = g.replace("_", " ")
        rows = sorted([r for r in rows if r[1] > 0], key=lambda r: -r[1])[:5]
        if rows:
            cols_, trs = [], []
            for n, c_, p_ in rows:
                p = None if not p_ else round((c_ - p_) / abs(p_) * 100, 1)
                cols_.append(NEUTRAL if target is None else GREEN if p is not None and p >= UP_PCT else RED if p is not None and p <= DOWN_PCT else ORANGE)
                trs.append({"name": n, "value": _r(c_), "change": pct_s(p) if target is not None else ""})
            sections.append({"id": "ranking", "title": f"Top {len(rows)} by {gname}", "tone": "neutral", "color": NEUTRAL,
                             "chart": {"type": "bar", "labels": [r[0] for r in rows], "values": [_r(r[1]) for r in rows], "colors": cols_,
                                       "color": NEUTRAL, "format": fmt},
                             "table": {"columns": [{"key": "name", "label": gname.capitalize()}, {"key": "value", "label": label, "format": fmt}]
                                       + ([{"key": "change", "label": f"vs {_period_label(prev, 'month')}"}] if target is not None else []),
                                       "rows": trs}})
            facts["ranking"] = {"grouped_by": gname, "top": [f"{t['name']}: {F(t['value'])}" + (f" ({t['change']})" if t["change"] else "") for t in trs]}
            steps.append(f"Ranked the top {len(rows)} by {gname}")

    # ---- stock ------------------------------------------------------------------
    if "quantity" in m and "reorder_level" in m:
        qc, rc, lab = m["quantity"], m["reorder_level"], label_column(profile)
        cond = f"{num(qc)} <= {num(rc)}"
        total, _ = _run(con, f"SELECT COUNT(*) FROM t WHERE {cond}", [])
        n_low = total[0][0]
        sel = ([q(lab)] if lab else []) + [q(qc), q(rc)]
        rows = _run(con, f"SELECT {', '.join(sel)} FROM t WHERE {cond} ORDER BY {num(qc)} - {num(rc)} ASC LIMIT 5", [])[0] if n_low else []
        items = [((str(r[0]) if lab else f"Item {i + 1}"), float(r[-2] or 0), float(r[-1] or 0)) for i, r in enumerate(rows)]
        stone = "watch" if n_low else "positive"
        sec = {"id": "stock", "title": "Stock to watch", "tone": stone, "color": TONE_COLOR[stone]}
        if items:
            sec["chart"] = {"type": "bar", "labels": [n for n, _, _ in items], "values": [_r(a) for _, a, _ in items],
                            "colors": [RED if a <= 0 else ORANGE for _, a, _ in items], "color": ORANGE, "format": "number",
                            "reference": [_r(b) for _, _, b in items]}
            sec["table"] = {"columns": [{"key": "name", "label": (lab or "item").replace("_", " ").capitalize()},
                                        {"key": "qty", "label": "In stock"}, {"key": "reorder", "label": "Reorder level"}],
                            "rows": [{"name": n, "qty": _r(a), "reorder": _r(b)} for n, a, b in items]}
        sections.append(sec)
        facts["stock"] = {"items_at_or_below_reorder": str(n_low),
                          "most_urgent": [f"{n}: {a:g} left, reorder level {b:g}" for n, a, b in items] or ["none"]}
        steps.append("Checked which items are at or below their reorder level")

    if not sections:
        raise PlanError("I couldn't build an overview from this sheet. It needs a date column, a category or product column, or stock levels.")

    # overall tone: trend decides, otherwise worst of the rest
    order = {"negative": 3, "watch": 2, "positive": 1, "neutral": 0}
    tone = next((s["tone"] for s in sections if s["id"] == "trend"), None) or max((s["tone"] for s in sections), key=lambda t: order[t])
    if tone == "positive" and any(s["tone"] == "watch" for s in sections if s["id"] in ("share", "stock")):
        tone = "watch" if not chg or (chg.get("pct") or 0) < 10 else tone
    headline = {"value": facts["trend"]["value"] if "trend" in facts else None}
    if "trend" in facts and chg:
        headline = {"text": facts["trend"]["month"], "value": _r(by.get(target, 0.0)), "format": fmt}
    result = {"kind": "report", "title": f"{label} overview", "tone": tone, "color": TONE_COLOR[tone], "headline": headline,
              "sections": sections, "steps": steps, "sheet": sheet_name, "_facts": facts, "_label": label}
    if chg:
        result["change"] = chg
    if note:
        result["steps"].append(note)
    return result


# ------------------------------------------------------------------ narrative
def _allowed_numbers(facts):
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*\.?\d*", str(facts))}


def _clean(text):
    text = re.sub(r"[`#_>~]|\*\*\s*\*\*", "", str(text))
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)  # drop lone asterisks, keep **bold**
    if text.count("**") % 2:
        text = text.replace("**", "")
    return text.strip()


def _numbers_ok(text, allowed):
    return all(n.replace(",", "").rstrip(".") in allowed for n in re.findall(r"\d[\d,]*\.?\d*", text))


def rule_narrative(result):
    """Deterministic fallback: still bold-highlights what matters. Used when the AI is down or its numbers don't check out."""
    f, secs = result["_facts"], {}
    t = f.get("trend")
    if t:
        down = (result.get("change") or {}).get("direction") == "down"
        secs["trend"] = (f"**{t['month']}** came in at **{t['value']}**, **{t['change_pct']}** versus {t['previous_month']} ({t['previous_value']}). "
                         f"The strongest month was {t['best_month']} and the weakest was {t['weakest_month']}."
                         + (f" **Caution:** {t['data_note']}, so this comparison understates the month." if t["data_note"] else
                            " This is a **decline** worth investigating." if down else ""))
    dr = f.get("drivers")
    if dr:
        secs["drivers"] = (f"By {dr['grouped_by']}, the biggest drops were **{'; '.join(dr['biggest_drops'])}**, "
                           f"while gains came from {'; '.join(dr['biggest_gains'])}.")
    sh = f.get("share")
    if sh:
        secs["share"] = (f"**{sh['leader']}** leads {sh['period']}. " + (f"**Concentration risk:** {sh['concentration_risk']}." if sh["concentration_risk"]
                                                                          else f"Top three: {', '.join(sh['top_three'])}."))
    rk = f.get("ranking")
    if rk:
        secs["ranking"] = f"Top by {rk['grouped_by']}: " + "; ".join(rk["top"][:3]) + "."
    st = f.get("stock")
    if st:
        n = st["items_at_or_below_reorder"]
        secs["stock"] = (f"**{n} item(s)** are at or below their reorder level. Most urgent: {st['most_urgent'][0]}." if n != "0"
                         else "No items are at or below their reorder level.")
    if t:
        head = f"{t['month']}: {t['value']} ({t['change_pct']} vs {t['previous_month']})"
        summary = secs["trend"]
    else:
        head = result["title"]
        summary = next(iter(secs.values()))
    watch = [x for x in (
        t and t["data_note"], sh and sh["concentration_risk"],
        st and st["items_at_or_below_reorder"] != "0" and f"{st['items_at_or_below_reorder']} item(s) need reordering") if x][:3]
    return {"headline": head, "summary": summary, "sections": secs, "takeaways": [], "watch": watch}


def write_narrative(question, result, currency):
    """-> (narrative dict, provider). Falls back to rules if the AI is down or invents a number."""
    facts = result["_facts"]
    allowed = _allowed_numbers(facts)
    try:
        data, provider = ai.write_report(question, facts, currency)
        secs = {k: _clean(v) for k, v in (data.get("sections") or {}).items() if k in facts and isinstance(v, str)}
        out = {"headline": _clean(data.get("headline", "")), "summary": _clean(data.get("summary", "")), "sections": secs,
               "takeaways": [_clean(x) for x in (data.get("takeaways") or []) if isinstance(x, str)][:4],
               "watch": [_clean(x) for x in (data.get("watch") or []) if isinstance(x, str)][:3]}
        texts = [out["headline"], out["summary"], *secs.values(), *out["takeaways"], *out["watch"]]
        if not out["summary"] or not secs or not all(_numbers_ok(x, allowed) for x in texts):
            raise ai.AIUnavailable("narrative failed checks")
        return out, provider
    except (ai.AIUnavailable, AttributeError, TypeError):
        return rule_narrative(result), "rules"


def finish(result, narrative):
    """Merge the narrative into the card. Strips internal fields."""
    for s in result["sections"]:
        s["text"] = narrative["sections"].get(s["id"], "")
    card = {k: v for k, v in result.items() if not k.startswith("_")}
    card["headline_text"] = narrative["headline"]
    card["text"] = narrative["summary"]
    card["takeaways"] = narrative["takeaways"]
    card["watch"] = narrative["watch"]
    return card