"""The /ask pipeline: limits -> cache -> rules -> AI plan -> run -> explain -> save."""
import datetime as dt
import hashlib
import logging
import os
import re

from fastapi import HTTPException

import ai
import db
import report
from plans import PlanError, followups, is_projection, template_plan, validate_plan
from runner import run_plan
from sheet_picker import pick_sheet

log = logging.getLogger("beaver.answer")
BUCKET = "sheets"
FREE_LIMIT = int(os.getenv("FREE_QUESTION_LIMIT", "25"))
DAILY_USER_CAP = int(os.getenv("DAILY_USER_CAP", "30"))
GLOBAL_DAILY_CAP = int(os.getenv("GLOBAL_DAILY_CAP", "800"))
HELP_TEXT = ("I answer questions about the spreadsheets you've added. Try asking about totals, top items, "
             "comparisons with last month, or what's running low in stock.")
SMALLTALK = [
    (re.compile(r"^(hi|hello|hey|hiya|yo|sup|howdy|hello there|hi there|hey there|good (morning|afternoon|evening))( beaver)?$"),
     "Hello! " + HELP_TEXT),
    (re.compile(r"^(thanks|thank you|thank you so much|thanks a lot|thx|cheers|great thanks|ok thanks)( beaver)?$"),
     "You're welcome! Ask me anything else about your sheets."),
    (re.compile(r"^(who are you|what are you|what is beaver|what can you do|what do you do|help|help me|how does this work|how do i use this)$"),
     HELP_TEXT),
]
COMING_SOON = "Projections are coming soon. For now Beaver answers questions about the data you already have."


def today_start():
    return dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def questions_today(uid=None):
    params = {"select": "id", "created_at": f"gte.{today_start()}", "provider": "neq.cache", "limit": "20000"}
    if uid:
        params["user_id"] = f"eq.{uid}"
    return len(db.select("usage", params))


def normalize(question):
    return " ".join(re.findall(r"[a-z0-9]+", question.lower()))


def message(text):
    return {"counted": False, "card": {"kind": "message", "title": "Beaver", "message": text, "steps": []}}


def ask(uid, profile, question):
    question = (question or "").strip()
    if not question:
        raise HTTPException(400, "Type a question first.")
    if len(question) > 500:
        raise HTTPException(400, "Please keep your question under 500 characters.")
    for pattern, reply in SMALLTALK:  # greetings never reach the AI or use up a free question
        if pattern.match(normalize(question)):
            return message(reply)
    if is_projection(question):
        return message(COMING_SOON)

    rows = db.select("sheets", {"select": "id,name,storage_path,version,profile", "user_id": f"eq.{uid}"})
    if not rows:
        raise HTTPException(400, "Add a spreadsheet first, then ask your question.")
    by_id = {r["id"]: r for r in rows}

    version_key = ",".join(sorted(f"{r['id']}:{r['version']}" for r in rows))
    cache_key = hashlib.sha256(f"{uid}|{version_key}|{normalize(question)}".encode()).hexdigest()
    hit = db.select("answers", {"select": "id,question,card,provider", "cache_key": f"eq.{cache_key}", "limit": "1"})
    if hit:
        return {"counted": False, "cached": True, "id": hit[0]["id"], "card": hit[0]["card"]}

    if profile["questions_used"] >= FREE_LIMIT:
        raise HTTPException(402, f"You've used all {FREE_LIMIT} free questions. Thanks for trying Beaver! Paid plans are coming soon.")
    if questions_today(uid) >= DAILY_USER_CAP:
        raise HTTPException(429, "You've reached today's question limit. Please try again tomorrow.")
    if questions_today() >= GLOBAL_DAILY_CAP:
        raise HTTPException(503, "Beaver is very busy today. Please try again tomorrow.")

    cands = [{"id": r["id"], "name": r["name"], "profile": r["profile"]} for r in rows]
    picked = pick_sheet(question, cands)
    provider, plan, sheet = "rules", None, None

    if report.is_report_question(question):  # multi-step analysis: several verified calculations + a written report
        sid = picked["sheet_id"] if picked["status"] == "picked" else (
            picked["scores"][0]["sheet_id"] if picked["scores"][0]["score"] > 0 else None)
        if not sid:
            return message("I couldn't tell which of your sheets that question is about. Mention the sheet name and try again.")
        sheet = by_id[sid]
        currency = profile.get("currency", "USD")
        try:
            result = report.run_report(sheet["profile"], db.storage_download(BUCKET, sheet["storage_path"]), sheet["name"], question, currency)
        except PlanError as e:
            return message(str(e))
        narrative, provider = report.write_narrative(question, result, currency)
        card = {**report.finish(result, narrative), "followups": followups(sheet["profile"]), "currency": currency,
                "plan": {"sheet_id": sheet["id"], "operation": "report"}}
        return _save(uid, profile, question, cache_key, card, provider)

    try:
        if picked["status"] == "picked":
            sheet = by_id[picked["sheet_id"]]
            plan = template_plan(question, sheet["id"], sheet["profile"])
        if plan is None:
            if picked["status"] == "picked":
                pool = [c for c in cands if c["id"] == picked["sheet_id"]]
            else:
                pool = [c for c in cands if c["id"] in picked.get("candidates", [])] or cands
            try:
                raw, provider = ai.plan_question(question, pool)
            except ai.AIUnavailable:
                # rules-only fallback: best-scoring sheet, template questions only
                best = by_id[picked["scores"][0]["sheet_id"]]
                plan = template_plan(question, best["id"], best["profile"]) if picked["scores"][0]["score"] > 0 or len(rows) == 1 else None
                if plan is None:
                    raise HTTPException(503, "Beaver is busy, try again soon.")
                sheet, provider = best, "rules"
            else:
                if raw.get("unsupported") == "projection":
                    return message(COMING_SOON)
                if raw.get("unsupported"):
                    return message("I can't answer that one yet. Try asking about totals, top items, comparisons with last month, or low stock.")
                sheet = by_id.get(raw.get("sheet_id"))
                if not sheet:
                    return message("I couldn't tell which of your sheets that question is about. Mention the sheet name and try again.")
                plan = validate_plan(raw, sheet["profile"])
        plan["sheet_id"] = sheet["id"]
        data = db.storage_download(BUCKET, sheet["storage_path"])
        result = run_plan(plan, sheet["profile"], data, sheet["name"])
    except PlanError as e:
        return message(str(e))

    currency = profile.get("currency", "USD")
    try:
        text, takeaways = ai.explain(question, result, currency) if result["kind"] != "empty" else (result["message"], [])
    except ai.AIUnavailable:
        text, takeaways = ai.basic_explanation(result) if result["kind"] != "empty" else (result["message"], [])
    card = {**result, "text": text, "takeaways": takeaways, "followups": followups(sheet["profile"]),
            "currency": currency, "plan": plan}

    return _save(uid, profile, question, cache_key, card, provider)


def _save(uid, profile, question, cache_key, card, provider):
    saved = db.insert("answers", {"user_id": uid, "question": question, "cache_key": cache_key, "card": card, "provider": provider})
    db.insert("usage", {"user_id": uid, "question": question[:200], "provider": provider})
    used = profile["questions_used"] + 1
    db.update("profiles", {"id": f"eq.{uid}"}, {"questions_used": used})
    return {"counted": True, "id": saved["id"], "card": card, "questions_used": used, "limit": FREE_LIMIT}