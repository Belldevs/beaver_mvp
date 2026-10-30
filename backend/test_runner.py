"""Checks DuckDB answers against plain pandas maths. Needs: pip install -r requirements.txt
Run: python test_runner.py"""
import io
import pandas as pd
from runner import run_plan

def pq(df):
    b = io.BytesIO(); df.to_parquet(b); return b.getvalue()

def col(n, t="text"): return {"name": n, "type": t}
inv = pd.DataFrame({"product": ["A", "B", "C"], "quantity": [10, 2, 5], "unit_cost": [2.5, 10.0, 4.0], "reorder_level": [5, 5, 5]})
IP = {"columns": [col("product"), col("quantity", "integer"), col("unit_cost", "float"), col("reorder_level", "integer")],
      "mapped_fields": {"product": "product", "quantity": "quantity", "unit_cost": "unit_cost", "reorder_level": "reorder_level"}}
r = run_plan({"operation": "total", "metric": "inventory_value", "filters": []}, IP, pq(inv), "Inv")
assert r["headline"]["value"] == 10 * 2.5 + 2 * 10 + 5 * 4, r
r = run_plan({"operation": "low_stock", "filters": []}, IP, pq(inv), "Inv")
assert r["headline"]["value"] == 2 and [x["name"] for x in r["table"]["rows"]] == ["B", "C"], r
r = run_plan({"operation": "top_n", "metric": "inventory_value", "group_field": "product", "n": 2, "filters": []}, IP, pq(inv), "Inv")
assert r["table"]["rows"][0]["name"] == "A", r

sales = pd.DataFrame({"date": pd.to_datetime(["2026-09-03", "2026-09-20", "2026-10-05", "2026-10-06"]),
                      "quantity": [1, 2, 3, 4], "price": [10.0, 10.0, 20.0, 5.0]})
SP = {"columns": [col("date", "date"), col("quantity", "integer"), col("price", "float")],
      "mapped_fields": {"date": "date", "quantity": "quantity", "price": "price"}}
r = run_plan({"operation": "compare_periods", "metric": "revenue", "period": {"unit": "month"}, "filters": []}, SP, pq(sales), "Sales")
assert r["headline"]["value"] == 80.0 and r["change"]["amount"] == 50.0 and r["change"]["pct"] == 166.7, r
assert len(r["chart"]["values"]) == 6 and r["chart"]["values"][-2:] == [30.0, 80.0], r["chart"]
r = run_plan({"operation": "total", "metric": "revenue", "filters": [{"field": "date", "op": "gte", "value": "2026-10-01"}]}, SP, pq(sales), "Sales")
assert r["headline"]["value"] == 80.0, r
r = run_plan({"operation": "total", "metric": "revenue", "filters": [{"field": "date", "op": "gte", "value": "2030-01-01"}]}, SP, pq(sales), "Sales")
assert r["kind"] == "empty", r
print("all runner tests passed")
