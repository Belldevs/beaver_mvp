"""Run: python test_plans.py   (no server, no AI, no database needed)"""
import datetime as dt
from plans import PlanError, template_plan, validate_plan, is_projection

def col(n, t="text"): return {"name": n, "type": t}
INV = {"columns": [col("product"), col("quantity", "integer"), col("unit_cost", "float"), col("price", "float"), col("reorder_level", "integer"), col("category")],
       "mapped_fields": {"product": "product", "quantity": "quantity", "unit_cost": "unit_cost", "price": "price", "reorder_level": "reorder_level", "category": "category"}}
SALES = {"columns": [col("date", "date"), col("product"), col("quantity", "integer"), col("price", "float"), col("region")],
         "mapped_fields": {"date": "date", "product": "product", "quantity": "quantity", "price": "price"}}
EXP = {"columns": [col("date", "date"), col("expense_type"), col("amount", "float")], "mapped_fields": {"date": "date"}}
TODAY = dt.date(2026, 11, 5)

def plan(q, p): return template_plan(q, "s1", p, TODAY)

def test():
    p = plan("What is our total inventory value?", INV); assert (p["operation"], p["metric"]) == ("total", "inventory_value"), p
    p = plan("Which products are running low in stock and should be reordered soon?", INV); assert p["operation"] == "low_stock"
    p = plan("How did sales compare to last month?", SALES); assert (p["operation"], p["metric"]) == ("compare_periods", "revenue"), p
    p = plan("What were our top products last month?", SALES)
    assert p["operation"] == "top_n" and p["group_field"] == "product" and p["metric"] == "revenue"
    assert [f["value"] for f in p["filters"]] == ["2026-10-01", "2026-11-01"], p["filters"]
    p = plan("Top 3 products by revenue", SALES); assert p["n"] == 3
    p = plan("Show revenue by region", SALES); assert (p["operation"], p["group_field"]) == ("group_by", "region"), p
    p = plan("How much did we spend this year?", EXP); assert p["metric"] == "amount" and p["filters"][0]["value"] == "2026-01-01"
    assert plan("tell me something nice", INV) is None
    # missing fields -> clear message, never a guess
    for q, prof, frag in [("What is our total inventory value?", EXP, "quantity"), ("Which items are low in stock?", SALES, "reorder level"),
                          ("How did sales compare to last month?", INV, "date")]:
        try: plan(q, prof); raise SystemExit(f"expected PlanError: {q}")
        except PlanError as e: assert frag in str(e), str(e)
    # AI-made plans are validated: unknown columns / ops are rejected
    for bad in [{"operation": "total", "metric": "sum:secret"}, {"operation": "drop_table"},
                {"operation": "total", "filters": [{"field": "nope", "op": "eq", "value": 1}]},
                {"operation": "total", "filters": [{"field": "price", "op": "; DROP", "value": 1}]}]:
        try: validate_plan(bad, SALES); raise SystemExit(f"expected PlanError: {bad}")
        except PlanError: pass
    assert is_projection("Calculate net profit at the end of this fiscal year") and not is_projection("What is our total revenue?")
    print("all plan tests passed")

test()
