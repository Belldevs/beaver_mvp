"""Run: python test_report.py  (no AI, database or DuckDB needed for these checks)"""
import datetime as dt
import pandas as pd
import report, ai

assert report.is_report_question("Give me a summary of how the business did in September")
assert report.is_report_question("Why did October revenue drop compared to September?")
assert report.is_report_question("how is revenue trending across all months?")
assert not report.is_report_question("What is our total inventory value?")
assert report.tone_for(5) == "positive" and report.tone_for(-8) == "negative" and report.tone_for(-1) == "watch"
assert report.tone_for(-20, partial=True) == "watch"
months = {pd.Timestamp(2026, m, 1) for m in range(5, 11)}
t, p, _ = report._target_months("Why did October drop compared to September?", months, dt.date(2026, 11, 5))
assert (t.month, p.month) == (10, 9)
t, p, _ = report._target_months("summary", months, dt.date(2026, 11, 5)); assert t.month == 10
assert report._per_point_colors([100, 120, 100, 99]) == [report.NEUTRAL, report.GREEN, report.RED, report.ORANGE]
assert report.money(1234.5, "currency", "NGN") == "₦1,234" or report.money(1234.5, "currency", "NGN") == "₦1,235"

facts = {"trend": {"month": "Oct 2026", "value": "$8,000", "previous_month": "Sep 2026", "previous_value": "$10,000", "change": "-$2,000",
                   "change_pct": "-20.0%", "best_month": "Aug 2026 ($12,000)", "weakest_month": "Oct 2026 ($8,000)", "months_covered": "6", "data_note": ""},
         "stock": {"items_at_or_below_reorder": "2", "most_urgent": ["Rice: 1 left, reorder level 5"]}}
result = {"kind": "report", "title": "Revenue overview", "tone": "negative", "color": report.RED, "headline": {}, "steps": [], "sheet": "S",
          "change": {"direction": "down", "pct": -20.0},
          "sections": [{"id": "trend", "title": "t"}, {"id": "stock", "title": "s"}], "_facts": facts, "_label": "Revenue"}
n = report.rule_narrative(result)
assert "**$8,000**" in n["sections"]["trend"] and "decline" in n["sections"]["trend"] and n["watch"]
# a made-up number makes the AI narrative fall back to rules
ai.write_report = lambda *a: ({"headline": "Sales fell", "summary": "Revenue fell by **$3,500**.", "sections": {"trend": "x"}}, "gemini")
assert report.write_narrative("why?", result, "USD")[1] == "rules"
ai.write_report = lambda *a: ({"headline": "Revenue fell **-20.0%**", "summary": "October hit **$8,000** from $10,000.",
                               "sections": {"trend": "**Oct 2026** is the weakest month.", "bogus": "ignored"}, "takeaways": ["Reorder Rice."], "watch": []}, "gemini")
n, prov = report.write_narrative("why?", result, "USD")
assert prov == "gemini" and set(n["sections"]) == {"trend"}
card = report.finish(result, n)
assert card["sections"][0]["text"].startswith("**Oct") and "_facts" not in card and card["text"]
print("all report tests passed")