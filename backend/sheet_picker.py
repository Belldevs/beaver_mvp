"""Rules-first sheet picking. No AI, no network.

pick_sheet(question, sheets) where each sheet is {"id", "name", "profile"} and "profile" is the
profile card saved at upload time (only column names, types, mapped fields and aggregates).

Returns:
  {"status": "picked" | "ambiguous",
   "sheet_id": ... (only when picked),
   "candidates": [sheet ids worth asking the AI about] (when ambiguous),
   "reason": "only_sheet" | "clear_winner" | "close_scores" | "no_signal",
   "scores": [{"sheet_id", "name", "score", "why": [...]}, ...] best first}
"""
import re

STOPWORDS = set("""
a an the is are was were be been am do does did has have had can could should would will shall
i me my mine we our ours you your it its they them their he she this that these those there here
what which who whom whose when where why how much many more most any all some each every
of in on at to for by from with about into over under between than then so as if or and but not no
last next past current show tell give list get see find me please us just also still yet
""".split())

# Words that appear in lots of sheets, so a match tells us little.
GENERIC = {"product", "item", "name", "total", "number", "count", "amount", "date", "month", "week",
           "year", "day", "quarter", "type", "category", "report", "data", "sheet", "value"}

# The synonym list: each concept is a kind of sheet. A question word and a sheet word
# that fall in the same concept count as a match ("stock" ~ "inventory", "spend" ~ "expenses").
CONCEPTS = {
    "stock": """stock inventory reorder restock replenish stockout shelf warehouse remaining left
                available low out running supply supplies""",
    "sales": """sale sales sold sell selling revenue income turnover order orders customer customers
                client buyer bought buy invoice receipt transaction takings bestseller earn earned earnings""",
    "expenses": """expense expenses expenditure spend spent spending bill bills rent salary salaries wage
                   wages payroll overhead overheads utility utilities electricity fuel paid pay payment
                   outgoing cost costs""",
    "price": """price pricing markup cost""",
    "time": """month monthly week weekly quarter year yearly daily today yesterday trend growth grow grew
               change compare versus vs increase decrease""",
}
# Words that point at more than one kind of sheet (so the result should be ambiguous).
CROSS = {"profit": ["sales", "expenses"], "margin": ["sales", "expenses"], "net": ["sales", "expenses"]}

# A mapped standard field also tells us what a column is about.
FIELD_CONCEPT = {"quantity": "stock", "reorder_level": "stock", "unit_cost": "price", "price": "price",
                 "date": "time"}


def stem(w: str) -> str:
    w = w.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ing") and len(w) > 5:
        w = w[:-3]
        if len(w) > 2 and w[-1] == w[-2] and w[-1] not in "lsz":
            w = w[:-1]
        return w
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def words(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", str(text).lower()) if t]


def stems(text: str, drop_stop=True) -> list[str]:
    return [stem(t) for t in words(text) if not (drop_stop and t in STOPWORDS)]


WORD_CONCEPTS: dict[str, set[str]] = {}
for _concept, _ws in CONCEPTS.items():
    for _w in _ws.split():
        WORD_CONCEPTS.setdefault(stem(_w), set()).add(_concept)
for _w, _cs in CROSS.items():
    WORD_CONCEPTS.setdefault(stem(_w), set()).update(_cs)


def concepts_of(stem_list) -> set[str]:
    out: set[str] = set()
    for s in stem_list:
        out |= WORD_CONCEPTS.get(s, set())
    return out


def score_sheet(q_stems: list[str], q_concepts: set[str], sheet: dict):
    profile = sheet.get("profile") or {}
    why: list[str] = []
    score = 0.0

    # 1) the sheet's name (strongest signal)
    name_stems = set(stems(sheet["name"], drop_stop=False))
    name_concepts = concepts_of(name_stems)
    credited: set[str] = set()
    for s in dict.fromkeys(q_stems):
        if s in name_stems and s not in GENERIC:
            score += 4
            why.append(f"sheet name has '{s}'")
            credited |= WORD_CONCEPTS.get(s, set())
    for c in (q_concepts & name_concepts) - credited - {"time", "price"}:
        score += 3
        why.append(f"sheet name is about {c}")

    # 2) the column names
    col_stems: set[str] = set()
    for col in profile.get("columns", []):
        col_stems |= set(stems(col.get("original_name", ""), drop_stop=False))
        col_stems |= set(stems(col["name"].replace("_", " "), drop_stop=False))
    col_concepts = concepts_of(col_stems) | {FIELD_CONCEPT[f] for f in profile.get("mapped_fields", {})
                                             if f in FIELD_CONCEPT}
    credited = set()
    for s in dict.fromkeys(q_stems):
        if s in col_stems:
            generic = s in GENERIC
            score += 0.5 if generic else 2
            why.append(f"a column has '{s}'" + (" (generic)" if generic else ""))
            credited |= WORD_CONCEPTS.get(s, set())
    for c in (q_concepts & col_concepts) - credited - {"time"}:
        score += 1.5
        why.append(f"columns are about {c}")

    # 3) questions about time favour sheets that have dates
    if "time" in q_concepts and "date" in profile.get("mapped_fields", {}):
        score += 0.5
        why.append("has a date column")
    return round(score, 2), why


def pick_sheet(question: str, sheets: list[dict]) -> dict:
    if not sheets:
        raise ValueError("No sheets to pick from.")
    q_stems = stems(question)
    q_concepts = concepts_of(q_stems)

    ranked = []
    for sh in sheets:
        sc, why = score_sheet(q_stems, q_concepts, sh)
        ranked.append({"sheet_id": sh["id"], "name": sh["name"], "score": sc, "why": why})
    ranked.sort(key=lambda r: -r["score"])

    base = {"scores": ranked}
    if len(sheets) == 1:
        return {**base, "status": "picked", "sheet_id": ranked[0]["sheet_id"], "reason": "only_sheet"}

    top, second = ranked[0]["score"], ranked[1]["score"]
    if top < 1.5:
        return {**base, "status": "ambiguous", "reason": "no_signal", "candidates": [r["sheet_id"] for r in ranked]}
    if top - second < max(1.5, 0.3 * top):
        cands = [r["sheet_id"] for r in ranked if r["score"] >= top * 0.5][:3]
        return {**base, "status": "ambiguous", "reason": "close_scores", "candidates": cands}
    return {**base, "status": "picked", "sheet_id": ranked[0]["sheet_id"], "reason": "clear_winner"}
