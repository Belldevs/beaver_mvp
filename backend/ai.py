"""AI calls with fallbacks: Gemini -> (retry once on 429) -> backup provider -> AIUnavailable.
The AI only ever sees column names, types, descriptions, and already-computed results. Never raw rows."""
import json
import logging
import os
import re
import time

import httpx

log = logging.getLogger("beaver.ai")
_http = httpx.Client(timeout=30)


class AIUnavailable(Exception):
    pass


def _gemini(system, user):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise AIUnavailable("no gemini key")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json"}}  # newer Gemini models deprecate temperature
    for attempt in (1, 2):
        r = _http.post(url, json=body, headers={"x-goog-api-key": key})
        if r.status_code == 429 and attempt == 1:
            time.sleep(2)  # wait briefly, retry once
            continue
        if r.status_code != 200:
            raise AIUnavailable(f"gemini {r.status_code}: {r.text[:200]}")
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError):
            raise AIUnavailable("gemini bad response")
    raise AIUnavailable("gemini 429")


def _backup(system, user):
    key = os.getenv("BACKUP_API_KEY")
    if not key:
        raise AIUnavailable("no backup key")
    base = os.getenv("BACKUP_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    body = {"model": os.getenv("BACKUP_MODEL", "llama-3.1-8b-instant"), "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    r = _http.post(f"{base}/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"})
    if r.status_code != 200:
        raise AIUnavailable(f"backup {r.status_code}: {r.text[:200]}")
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise AIUnavailable("backup bad response")


def complete_json(system, user):
    """-> (parsed_json, provider_name). Raises AIUnavailable if every provider fails."""
    for name, fn in (("gemini", _gemini), ("backup", _backup)):
        try:
            text = fn(system, user)
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            return json.loads(text), name
        except (AIUnavailable, httpx.HTTPError, ValueError) as e:
            log.warning("%s failed: %s", name, e)
    raise AIUnavailable("all providers failed")


PLAN_SYSTEM = """You turn a business question into a JSON query plan for a spreadsheet. Reply with JSON only.
You are given the user's sheets (names, columns, types, descriptions). You never see the data.
Plan: {"sheet_id": "<one of the given ids>",
 "operation": "total" | "top_n" | "group_by" | "compare_periods" | "low_stock" | "filter",
 "metric": "inventory_value" | "retail_value" | "revenue" | "quantity" | "count" | "amount" | "sum:<numeric column name>",
 "group_field": "<column name>", "n": <1-20>,
 "filters": [{"field": "<column name>", "op": "eq|neq|gt|gte|lt|lte|contains", "value": "<value>"}],
 "period": {"unit": "month" | "quarter" | "year"}}
Rules: use exact column names and sheet ids as given. metric/group_field/n/period only when the operation needs them.
compare_periods compares the latest period in the data with the one before it.
Forecasts, projections or predictions: reply {"unsupported": "projection"}.
Anything these operations cannot answer: reply {"unsupported": "other"}."""


def plan_question(question, sheets):
    """sheets: [{id, name, profile}]. -> (plan_dict_or_unsupported, provider)"""
    brief = [{"id": s["id"], "name": s["name"],
              "columns": [{"name": c["name"], "type": c["type"], "about": c.get("description", "")} for c in s["profile"]["columns"]],
              "mapped_fields": s["profile"].get("mapped_fields", {})} for s in sheets]
    user = f"Sheets: {json.dumps(brief)}\nQuestion: {question}"
    plan, provider = complete_json(PLAN_SYSTEM, user)
    if not isinstance(plan, dict):
        raise AIUnavailable("bad plan")
    return plan, provider


EXPLAIN_SYSTEM = """You explain verified spreadsheet results to a small business owner in plain English.
Use ONLY the numbers in the result; never calculate or invent anything. Reply with JSON only:
{"text": "1-2 short sentences answering the question", "takeaways": ["short point", "short point", "short point"]}"""


def summarize_for_ai(result):
    keep = {k: result.get(k) for k in ("kind", "title", "headline", "change", "message")}
    if result.get("chart"):
        keep["chart"] = {"labels": result["chart"]["labels"][:12], "values": result["chart"]["values"][:12]}
    if result.get("table"):
        keep["table_rows"] = result["table"]["rows"][:10]
    return keep


def explain(question, result, currency):
    data, _ = complete_json(EXPLAIN_SYSTEM, f"Question: {question}\nCurrency: {currency}\nResult: {json.dumps(summarize_for_ai(result), default=str)}")
    text = data.get("text")
    tk = [t for t in (data.get("takeaways") or []) if isinstance(t, str)][:3]
    if not isinstance(text, str) or not text.strip():
        raise AIUnavailable("bad explanation")
    return text.strip(), tk


def basic_explanation(result):
    """Plain fallback when no AI is available. Numbers are shown by the card itself."""
    k = result["kind"]
    if k == "compare":
        c = result["change"]
        word = {"up": "higher", "down": "lower", "flat": "unchanged"}[c["direction"]]
        return (f"This is {word} than {c['vs']}.", [])
    if k == "ranking":
        return (f"{result['headline']['text']} is at the top.", [])
    if k == "table":
        return (f"Here are the {result['headline']['value']} matching items.", [])
    return ("Here is your answer, calculated from your sheet.", [])


REPORT_SYSTEM = """You are Beaver, a sharp business analyst writing a short report for a small business owner.
You are given VERIFIED facts (already calculated, already formatted). Write the words only. Reply with JSON only:
{"headline": "one punchy verdict line, max 14 words",
 "summary": "2-4 sentences: lead with the verdict, then the main cause, then what to do next",
 "sections": {"<section id from the facts>": "1-3 sentences interpreting that section"},
 "takeaways": ["up to 4 specific, actionable points"],
 "watch": ["up to 3 risks or things to look out for; empty list if none"]}
Rules:
- Copy numbers EXACTLY as written in the facts (same symbols, commas, signs). Never calculate, round, convert or invent a number.
- Mention only facts you were given. Say what happened and where it came from; do not claim causes the facts do not show.
- If data_note says the month is incomplete, say so plainly and do not call the drop a real decline.
- Put **double asterisks** around the words a business owner must take seriously: sharp drops, risks, shortfalls, concentration, key figures. Use them sparingly (3-6 per answer). No other markdown, no emojis.
- Write like an analyst: direct, specific, confident. No filler such as "Here is", "Certainly" or "Great question". Name products and categories.
- Only include sections that appear in the facts."""


def write_report(question, facts, currency):
    """-> (dict, provider). The AI sees only pre-computed, pre-formatted facts."""
    data, provider = complete_json(REPORT_SYSTEM, f"Question: {question}\nCurrency: {currency}\nFacts: {json.dumps(facts, default=str)}")
    if not isinstance(data, dict):
        raise AIUnavailable("bad report")
    return data, provider