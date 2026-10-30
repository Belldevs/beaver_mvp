"""Run a validated plan against a sheet's Parquet data with DuckDB. All math happens here, in code.
Values are always passed as query parameters; column names only come from the sheet's own profile."""
import io
import logging
import threading

import pandas as pd

from plans import (PlanError, columns, date_column, label_column, num, q, resolve_metric)

log = logging.getLogger("beaver.runner")
LIST_LIMIT = 50
TIMEOUT_S = 15
OFFSET = {"month": pd.DateOffset(months=1), "quarter": pd.DateOffset(months=3), "year": pd.DateOffset(years=1)}


def build_where(filters, profile):
    cols = columns(profile)
    sql, params, steps = [], [], []
    for f in filters:
        c, op, v = f["field"], f["op"], f["value"]
        t = cols[c]["type"]
        if op == "contains":
            esc = str(v).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql.append(f"lower(CAST({q(c)} AS VARCHAR)) LIKE ? ESCAPE '\\'")
            params.append(f"%{esc.lower()}%")
        else:
            sym = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
            if t in ("integer", "float"):
                try:
                    val = float(v)
                except (TypeError, ValueError):
                    raise PlanError(f"'{v}' isn't a number, but the {c} column is numeric.")
                sql.append(f"{num(c)} {sym} ?")
                params.append(val)
            elif t == "date":
                sql.append(f"CAST({q(c)} AS DATE) {sym} CAST(? AS DATE)")
                params.append(str(v)[:10])
            elif op in ("eq", "neq"):
                sql.append(f"lower(CAST({q(c)} AS VARCHAR)) {sym} lower(?)")
                params.append(str(v))
            else:
                sql.append(f"CAST({q(c)} AS VARCHAR) {sym} ?")
                params.append(str(v))
        steps.append(f"Filter: {c} {op} {v}")
    return ((" AND " + " AND ".join(sql)) if sql else ""), params, steps


def _period_label(ts, unit):
    if unit == "quarter":
        return f"Q{(ts.month - 1) // 3 + 1} {ts.year}"
    return str(ts.year) if unit == "year" else ts.strftime("%b %Y")


def _run(con, sql, params):
    import duckdb
    try:
        cur = con.execute(sql, params)
        return cur.fetchall(), [d[0] for d in cur.description]
    except duckdb.Error:
        log.exception("query failed: %s", sql)
        raise PlanError("I couldn't run that question on this sheet. Try rephrasing it.")


def _r(v, nd=2):
    return None if v is None else round(float(v), nd)


def run_plan(plan, profile, parquet_bytes, sheet_name):
    import duckdb
    df = pd.read_parquet(io.BytesIO(parquet_bytes))
    if len(df) > 500_000:
        raise PlanError("This sheet is too large to analyse.")
    con = duckdb.connect(":memory:")
    timer = threading.Timer(TIMEOUT_S, con.interrupt)
    timer.start()
    try:
        con.register("t", df)
        return _execute(con, plan, profile, sheet_name, df)
    finally:
        timer.cancel()
        con.close()


def _empty(profile, steps, sheet_name):
    rng = (profile.get("aggregates") or {}).get("date_range")
    msg = "No rows matched your question."
    if rng:
        msg += f" The dates in this sheet run from {rng['from']} to {rng['to']}."
    return {"kind": "empty", "title": "No data found", "message": msg, "steps": steps, "sheet": sheet_name}


def _execute(con, plan, profile, sheet_name, df):
    op, m = plan["operation"], profile.get("mapped_fields", {})
    where, params, steps = build_where(plan.get("filters", []), profile)
    steps = [f"Used the sheet '{sheet_name}'"] + steps
    W = f" WHERE 1=1{where}"

    if op in ("total", "top_n", "group_by", "compare_periods"):
        expr, label, fmt, mstep = resolve_metric(plan["metric"], profile)
        steps.append(mstep)

    if op == "total":
        rows, _ = _run(con, f"SELECT {expr}, COUNT(*) FROM t{W}", params)
        val, n = rows[0]
        if not n:
            return _empty(profile, steps, sheet_name)
        steps.append(f"Added up {n:,} rows")
        return {"kind": "number", "title": label, "headline": {"value": _r(val), "format": fmt},
                "steps": steps, "sheet": sheet_name}

    if op in ("top_n", "group_by"):
        g = plan["group_field"]
        lim = plan["n"] if op == "top_n" else LIST_LIMIT
        rows, _ = _run(con, f"SELECT {q(g)}, {expr} AS v FROM t{W} GROUP BY 1 ORDER BY v DESC NULLS LAST, 1 LIMIT {int(lim)}", params)
        if not rows:
            return _empty(profile, steps, sheet_name)
        steps.append(f"Grouped by {g} and sorted highest first" + (f", kept the top {lim}" if op == "top_n" else ""))
        items = [("(blank)" if k is None else str(k), _r(v)) for k, v in rows]
        return {"kind": "ranking", "title": f"{label} by {g.replace('_', ' ')}",
                "headline": {"text": items[0][0], "value": items[0][1], "format": fmt},
                "chart": {"labels": [k for k, _ in items], "values": [v for _, v in items], "format": fmt, "highlight": 0},
                "table": {"columns": [{"key": "name", "label": g.replace("_", " ").capitalize()},
                                      {"key": "value", "label": label, "format": fmt}],
                          "rows": [{"name": k, "value": v} for k, v in items]},
                "steps": steps, "sheet": sheet_name}

    if op == "compare_periods":
        d, unit = date_column(profile), plan["period"]["unit"]
        rows, _ = _run(con, f"SELECT date_trunc('{unit}', CAST({q(d)} AS TIMESTAMP)) AS p, {expr} AS v FROM t "
                            f"WHERE {q(d)} IS NOT NULL{where} GROUP BY 1 ORDER BY 1", params)
        if not rows:
            return _empty(profile, steps, sheet_name)
        by = {pd.Timestamp(p): (0.0 if v is None else float(v)) for p, v in rows}
        latest = max(by)
        off = OFFSET[unit]
        periods = [latest - off * k for k in range(5, -1, -1)]
        prev = periods[-2]
        cur_v, prev_v = by[latest], by.get(prev, 0.0)
        amount = cur_v - prev_v
        pct = round(amount / abs(prev_v) * 100, 1) if prev_v else None
        steps.append(f"Compared {_period_label(latest, unit)} with {_period_label(prev, unit)} "
                     f"(the latest {unit} in your data is {_period_label(latest, unit)})")
        if prev not in by:
            steps.append(f"There is no data for {_period_label(prev, unit)}, so it counts as 0")
        steps.append(f"Change = {_period_label(latest, unit)} minus {_period_label(prev, unit)}")
        return {"kind": "compare", "title": f"{label}: {_period_label(latest, unit)}",
                "headline": {"value": _r(cur_v), "format": fmt},
                "change": {"pct": pct, "amount": _r(amount), "direction": "up" if amount > 0 else "down" if amount < 0 else "flat",
                           "vs": f"{_period_label(prev, unit)}", "previous": _r(prev_v), "format": fmt},
                "chart": {"labels": [_period_label(p, unit) for p in periods], "values": [_r(by.get(p, 0.0)) for p in periods],
                          "format": fmt, "highlight": 5, "ranges": unit == "month"},
                "steps": steps, "sheet": sheet_name}

    if op == "low_stock":
        qc, rc, lab = m["quantity"], m["reorder_level"], label_column(profile)
        cond = f"{num(qc)} <= {num(rc)}"
        rows, _ = _run(con, f"SELECT COUNT(*) FROM t{W} AND {cond}", params)
        total = rows[0][0]
        steps.append(f"Low stock means {qc} is at or below {rc}")
        if not total:
            return {"kind": "number", "title": "Low stock items", "headline": {"value": 0, "format": "count", "suffix": "items low"},
                    "steps": steps, "sheet": sheet_name}
        sel = ([q(lab)] if lab else []) + [q(qc), q(rc)]
        rows, _ = _run(con, f"SELECT {', '.join(sel)} FROM t{W} AND {cond} ORDER BY {num(qc)} - {num(rc)} ASC LIMIT {LIST_LIMIT}", params)
        cols_ = ([{"key": "name", "label": (lab or "").replace("_", " ").capitalize()}] if lab else []) + [
            {"key": "qty", "label": "Current stock"}, {"key": "reorder", "label": "Reorder level"}, {"key": "status", "label": "Status"}]
        out = []
        for r in rows:
            r = list(r)
            nm = str(r.pop(0)) if lab else None
            row = {"qty": _r(r[0], 2), "reorder": _r(r[1], 2), "status": "Low"}
            if lab:
                row["name"] = nm
            out.append(row)
        steps.append("Sorted by how far below the reorder level each item is" + (f" (showing {LIST_LIMIT} of {total})" if total > LIST_LIMIT else ""))
        return {"kind": "table", "title": "Low stock items", "headline": {"value": total, "format": "count", "suffix": "items low"},
                "table": {"columns": cols_, "rows": out}, "steps": steps, "sheet": sheet_name}

    if op == "filter":
        names = [c["name"] for c in profile["columns"]]
        show = list(dict.fromkeys(([label_column(profile)] if label_column(profile) else []) + [f["field"] for f in plan.get("filters", [])]
                                  + names))[:5]
        rows, _ = _run(con, f"SELECT {', '.join(q(c) for c in show)} FROM t{W} LIMIT {LIST_LIMIT}", params)
        if not rows:
            return _empty(profile, steps, sheet_name)
        steps.append(f"Showing up to {LIST_LIMIT} matching rows")
        def cell(v):
            return v if isinstance(v, (int, float, str)) or v is None else str(v)
        return {"kind": "table", "title": "Matching rows", "headline": {"value": len(rows), "format": "count", "suffix": "rows shown"},
                "table": {"columns": [{"key": c, "label": c.replace("_", " ").capitalize()} for c in show],
                          "rows": [{c: cell(v) for c, v in zip(show, r)} for r in rows]},
                "steps": steps, "sheet": sheet_name}
    raise PlanError("I couldn't work out how to answer that.")
