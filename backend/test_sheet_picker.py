"""Run:  python test_sheet_picker.py     (or: pytest -s test_sheet_picker.py)

20 example questions with the sheet we expect. "AMBIGUOUS" means the question genuinely spans
sheets, so the rules should hand it to the AI step instead of guessing.
Profiles come from the real upload parser, so this tests the same cards the app stores.
"""
import pandas as pd

from parsing import parse_file
from sheet_picker import pick_sheet
from test_parsing import make_xlsx

AMBIGUOUS = "AMBIGUOUS"


def build(sheets: dict) -> list[dict]:
    parsed = parse_file(make_xlsx(sheets), "t.xlsx")
    return [{"id": p.name, "name": p.name, "profile": p.profile} for p in parsed]


WORKBOOK_A = build({
    "Inventory": pd.DataFrame({"Product": ["a", "b"], "SKU": ["1", "2"], "Qty": [5, 90], "Reorder Level": [20, 40],
                               "Unit Cost": [100, 200], "Selling Price": [150, 300], "Category": ["x", "y"]}),
    "Sales": pd.DataFrame({"Date": ["05/01/2026", "06/01/2026"], "Product": ["a", "b"], "Quantity": [2, 3],
                           "Price": [150, 300], "Customer": ["Ada", "Bayo"]}),
    "Expenses": pd.DataFrame({"Date": ["05/01/2026", "06/01/2026"], "Expense": ["Rent", "Power"],
                              "Category": ["Fixed", "Utilities"], "Amount": [5000, 1200]}),
})

WORKBOOK_B = build({
    "Stock List": pd.DataFrame({"Item": ["a", "b"], "Code": ["1", "2"], "On Hand": [5, 90], "Min Stock": [20, 40],
                                "Cost": [100, 200], "Retail": [150, 300]}),
    "Orders": pd.DataFrame({"Order Date": ["05/01/2026", "06/01/2026"], "Item": ["a", "b"], "Qty": [2, 3],
                            "Unit Price": [150, 300], "Customer": ["Ada", "Bayo"]}),
    "Overheads": pd.DataFrame({"Month": ["Jan", "Feb"], "Description": ["Rent", "Power"], "Amount Paid": [5000, 1200]}),
})

CASES = [
    (WORKBOOK_A, "What is our total inventory value?", "Inventory"),
    (WORKBOOK_A, "Which products are running low in stock and should be reordered soon?", "Inventory"),
    (WORKBOOK_A, "How did revenue change this quarter?", "Sales"),
    (WORKBOOK_A, "How did sales compare to last month?", "Sales"),
    (WORKBOOK_A, "What were our top selling products last month?", "Sales"),
    (WORKBOOK_A, "How much did we spend on rent this year?", "Expenses"),
    (WORKBOOK_A, "Are any costs unusually high?", "Expenses"),
    (WORKBOOK_A, "What is our total spend by category?", "Expenses"),
    (WORKBOOK_A, "How many units of each product do we have left?", "Inventory"),
    (WORKBOOK_A, "Who are our best customers?", "Sales"),
    (WORKBOOK_A, "Show items below their reorder level", "Inventory"),
    (WORKBOOK_A, "What was total revenue in October?", "Sales"),
    (WORKBOOK_A, "What is our biggest expense?", "Expenses"),
    (WORKBOOK_A, "How much profit did we make this month?", AMBIGUOUS),
    (WORKBOOK_B, "How much stock do we have of each item?", "Stock List"),
    (WORKBOOK_B, "Which items need restocking?", "Stock List"),
    (WORKBOOK_B, "What were our biggest orders last week?", "Orders"),
    (WORKBOOK_B, "How much did we pay for electricity last quarter?", "Overheads"),
    (WORKBOOK_B, "What is our total sales for the quarter?", "Orders"),
    (WORKBOOK_B, "Who bought the most last month?", "Orders"),
]


def grade(sheets, question, expected):
    r = pick_sheet(question, sheets)
    if r["status"] == "picked":
        got = r["sheet_id"]
        return ("right" if got == expected else "WRONG"), got, r
    if expected == AMBIGUOUS:
        return "right", AMBIGUOUS, r
    return ("deferred" if expected in r["candidates"] else "WRONG"), AMBIGUOUS, r


def test_twenty_questions():
    counts = {"right": 0, "deferred": 0, "WRONG": 0}
    for sheets, q, expected in CASES:
        verdict, got, r = grade(sheets, q, expected)
        counts[verdict] += 1
        print(f"{verdict:8} expected={expected:10} got={got:10} {q}")
        if verdict != "right":
            for s in r["scores"]:
                print(f"           {s['name']:10} {s['score']:5}  {s['why']}")
    print(counts)
    assert counts["WRONG"] == 0, "a wrong pick is worse than asking the AI"
    assert counts["right"] >= 18, f"only {counts['right']} of 20 picked directly"


def test_single_sheet_and_no_signal():
    one = [WORKBOOK_A[0]]
    assert pick_sheet("anything at all", one)["reason"] == "only_sheet"
    r = pick_sheet("hello there", WORKBOOK_A)
    assert r["status"] == "ambiguous" and r["reason"] == "no_signal" and len(r["candidates"]) == 3


if __name__ == "__main__":
    test_twenty_questions()
    test_single_sheet_and_no_signal()
    print("all good")
