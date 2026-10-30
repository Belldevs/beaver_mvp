"""Try the sheet picker on YOUR files and YOUR questions, with no server and no login.

  python try_picker.py inventory.xlsx sales.xlsx expenses.xlsx --questions my_questions.csv

my_questions.csv has two columns, with a header row:
  question,expected
  What is our total inventory value?,Inventory
  How much profit did we make?,AMBIGUOUS

"expected" is the sheet NAME you think should answer it (as shown in the file), or AMBIGUOUS.
"""
import argparse
import csv
import sys

from parsing import ParseError, parse_file
from sheet_picker import pick_sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--questions", required=True)
    ap.add_argument("--verbose", action="store_true", help="show scores for every question")
    args = ap.parse_args()

    sheets = []
    for path in args.files:
        try:
            with open(path, "rb") as f:
                parsed = parse_file(f.read(), path.replace("\\", "/").split("/")[-1])
        except ParseError as e:
            sys.exit(f"{path}: {e}")
        for p in parsed:
            sheets.append({"id": f"s{len(sheets) + 1}", "name": p.name, "profile": p.profile})
    names = {s["id"]: s["name"] for s in sheets}
    print("Sheets found:", ", ".join(names.values()), "\n")

    counts = {"right": 0, "deferred": 0, "WRONG": 0, "no expectation": 0}
    with open(args.questions, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            q = (row.get("question") or "").strip()
            if not q:
                continue
            exp = (row.get("expected") or "").strip()
            r = pick_sheet(q, sheets)
            if r["status"] == "picked":
                got = names[r["sheet_id"]]
                verdict = "no expectation" if not exp else ("right" if got.lower() == exp.lower() else "WRONG")
            else:
                got = "AMBIGUOUS"
                cand = [names[c].lower() for c in r["candidates"]]
                if not exp:
                    verdict = "no expectation"
                elif exp.upper() == "AMBIGUOUS":
                    verdict = "right"
                else:
                    verdict = "deferred" if exp.lower() in cand else "WRONG"
            counts[verdict] += 1
            print(f"{verdict:8} expected={exp or '-':14} got={got:14} {q}")
            if args.verbose or verdict == "WRONG":
                for s in r["scores"]:
                    print(f"           {s['name']:16} {s['score']:5}  {'; '.join(s['why'])}")
    total = sum(counts.values())
    print(f"\n{counts}  ({total} questions)")
    print("right = picked directly and correctly | deferred = unsure, handed to the AI step with the right sheet in the shortlist")
    print("WRONG = picked the wrong sheet, or unsure with the right sheet missing from the shortlist")


if __name__ == "__main__":
    main()
