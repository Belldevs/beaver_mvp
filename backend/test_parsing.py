"""Run:  python test_parsing.py   (or: pytest)"""
import io
import json

import pandas as pd

from parsing import ParseError, parse_file


def make_xlsx(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    return buf.getvalue()


INVENTORY = pd.DataFrame({
    "Product Name": ["Zebra Widget", "Quokka Gadget", "Narwhal Gizmo", "Okapi Doohickey"],
    "SKU": ["00123", "00124", "00125", "00126"],
    "Qty": [12, 100, 7, None],
    "Reorder Level": [50, 40, 30, 10],
    "Unit Cost": ["₦1,500", "₦2,000.50", "₦300", "₦50"],
    "Selling Price": [2000, 3000, 450, 80],
    "Category": ["A", "B", "A", "B"],
})
SALES = pd.DataFrame({
    "Date": ["05/01/2026", "06/01/2026", "07/02/2026", "08/02/2026"],
    "Product": ["Zebra Widget", "Quokka Gadget", "Zebra Widget", "Narwhal Gizmo"],
    "Quantity": [2, 3, 1, 4],
    "Price": [2000, 3000, 2000, 450],
})
EXPENSES = pd.DataFrame({"Item": ["Rent", "Power"], "Amount": [50000, 12000]})


def test_xlsx_three_sheets():
    data = make_xlsx({"Inventory": INVENTORY, "Sales": SALES, "Expenses": EXPENSES})
    sheets = parse_file(data, "Quarterly planning.xlsx")
    assert [s.name for s in sheets] == ["Inventory", "Sales", "Expenses"]

    inv = sheets[0].profile
    assert inv["row_count"] == 4
    assert inv["mapped_fields"] == {
        "sku": "sku", "reorder_level": "reorder_level", "unit_cost": "unit_cost",
        "price": "selling_price", "quantity": "qty", "product": "product_name",
        "category": "category"} , inv["mapped_fields"]
    cols = {c["name"]: c for c in inv["columns"]}
    assert cols["sku"]["type"] == "text"                 # ids are labels, never summed
    assert cols["unit_cost"]["type"] == "float"          # "₦1,500" parsed as a number
    assert cols["qty"]["missing"] == 1
    assert inv["currency"] == "NGN"
    # total_value = 12*1500 + 100*2000.5 + 7*300 (+ NaN row skipped)
    assert abs(inv["aggregates"]["total_value"] - (18000 + 200050 + 2100)) < 1e-6
    assert inv["aggregates"]["low_stock_count"] == 2     # 12<=50 and 7<=30
    assert inv["aggregates"]["product_count"] == 4

    sales = sheets[1]
    assert sales.profile["mapped_fields"]["date"] == "date"
    assert sales.profile["columns"][0]["type"] == "date"
    assert sales.profile["aggregates"]["date_range"]["from"] == "2026-01-05"  # day-first


def test_profile_never_contains_row_values():
    data = make_xlsx({"Inventory": INVENTORY})
    blob = json.dumps(parse_file(data, "x.xlsx")[0].profile)
    for secret in ["Zebra", "Quokka", "Narwhal", "Okapi", "Widget"]:
        assert secret not in blob


def test_csv_and_missing_fields():
    csv = b"Item,Amount\nRent,50000\nPower,12000\n"
    sheets = parse_file(csv, "expenses.csv")
    assert len(sheets) == 1 and sheets[0].name == "expenses"
    p = sheets[0].profile
    assert "quantity" not in p["mapped_fields"] and "total_value" not in p["aggregates"]


def test_csv_keeps_leading_zeros():
    csv = b"SKU,Qty\n00123,5\n00124,6\n"
    df = parse_file(csv, "s.csv")[0].df
    assert df["sku"].tolist() == ["00123", "00124"]


def test_title_row_above_header():
    raw = pd.DataFrame([["Q1 Report", None, None], ["Product", "Qty", "Price"], ["A", 5, 10], ["B", 6, 20]])
    buf = io.BytesIO()
    raw.to_excel(buf, index=False, header=False, engine="openpyxl")
    p = parse_file(buf.getvalue(), "t.xlsx")[0].profile
    assert [c["name"] for c in p["columns"]] == ["product", "qty", "price"]


def test_errors():
    for data, name in [(b"hello", "a.xlsx"), (b"a,b\n", "a.csv"), (b"x", "a.pdf")]:
        try:
            parse_file(data, name)
            raise AssertionError("should have failed: " + name)
        except ParseError:
            pass


if __name__ == "__main__":
    for fn in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        fn()
        print("ok", fn.__name__)
