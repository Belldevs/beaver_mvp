"""Parse an uploaded .xlsx/.csv into clean DataFrames plus a privacy-safe profile card.

PRIVACY RULE: a profile contains only column names, types, counts and aggregates
(min/max/mean/sum, date range, distinct counts). It never contains values from the rows.
"""
import io
import re
import warnings
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

MAX_ROWS = 500_000
MISSING_TOKENS = {"", "n/a", "na", "#n/a", "null", "none", "nan", "-", "--"}

# ---- standard fields Beaver understands (a file does NOT need all of them) ----
# Order matters: more specific fields are matched first.
FIELD_SYNONYMS = {
    "sku": ["sku", "item_code", "product_code", "barcode", "item_id", "product_id", "code"],
    "reorder_level": ["reorder_level", "reorder_point", "reorder_threshold", "reorder", "min_stock",
                      "minimum_stock", "min_qty", "threshold"],
    "unit_cost": ["unit_cost", "cost_price", "cost_per_unit", "buying_price", "purchase_price", "cost"],
    "price": ["price", "unit_price", "selling_price", "sale_price", "sales_price", "retail_price"],
    "quantity": ["quantity", "qty", "stock", "units", "in_stock", "stock_level", "quantity_on_hand",
                 "on_hand", "current_stock"],
    "product": ["product", "product_name", "item", "item_name", "description", "product_description", "name"],
    "category": ["category", "product_category", "type", "group", "department"],
    "date": ["date", "order_date", "sale_date", "transaction_date", "invoice_date", "created_at"],
}
NUMERIC_FIELDS = {"quantity", "reorder_level", "unit_cost", "price"}

SYMBOL_TO_CODE = {"₦": "NGN", "NGN": "NGN", "$": "USD", "USD": "USD",
                  "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP"}
CUR_RE = re.compile(r"₦|\$|€|£|\b(?:NGN|USD|EUR|GBP)\b")
CUR_STRIP_RE = re.compile(r"₦|\$|€|£|NGN|USD|EUR|GBP", re.IGNORECASE)
TEXT_ONLY_TOKENS = {"sku", "code", "barcode", "id", "phone", "zip", "postcode"}


class ParseError(ValueError):
    """A problem the user can understand and fix (shown in the app as-is)."""


@dataclass
class ParsedSheet:
    name: str
    df: pd.DataFrame
    profile: dict


# ------------------------------------------------------------------ reading files
def _read_csv(data: bytes) -> pd.DataFrame:
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
        if df.shape[1] == 1:  # maybe a ; or tab separated file
            try:
                alt = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, sep=None, engine="python")
                if alt.shape[1] > 1:
                    df = alt
            except Exception:
                pass
    except Exception:
        raise ParseError("We couldn't read this CSV. Check that it has a header row and is a normal CSV file.")
    return df


def _symbols_in_format(fmt: str) -> list[str]:
    found = re.findall(r"\[\$([^\]\-]+)[^\]]*\]", fmt)  # [$₦-46A] -> ₦  ([$-409] has no symbol)
    stripped = re.sub(r"\[[^\]]*\]", "", fmt)
    return found + CUR_RE.findall(stripped)


def _excel_currency_symbols(data: bytes) -> dict[str, list[str]]:
    """Currency symbols used in cell number formats, per sheet (first 60 rows)."""
    out: dict[str, list[str]] = {}
    try:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        for ws in wb.worksheets:
            found: list[str] = []
            for row in ws.iter_rows(min_row=1, max_row=60):
                for c in row:
                    fmt = getattr(c, "number_format", None)
                    if fmt and fmt != "General":
                        found += _symbols_in_format(fmt)
            out[ws.title] = found
        wb.close()
    except Exception:
        pass
    return out


def _read_tables(data: bytes, filename: str) -> list[tuple[str, pd.DataFrame, list[str]]]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        stem = re.sub(r"\.csv$", "", filename, flags=re.IGNORECASE) or "Sheet1"
        return [(stem, _read_csv(data), [])]
    if lower.endswith(".xlsx"):
        if data[:2] != b"PK":
            raise ParseError("This doesn't look like a real .xlsx file. Open it in Excel and save it as .xlsx again.")
        try:
            sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, engine="openpyxl")
        except Exception:
            raise ParseError("We couldn't open this Excel file. It may be damaged or password-protected.")
        fmts = _excel_currency_symbols(data)
        return [(str(name), df, fmts.get(str(name), [])) for name, df in sheets.items()]
    raise ParseError("Only .xlsx and .csv files are supported.")


# ------------------------------------------------------------------ cleaning helpers
def normalize_name(s) -> str:
    s = re.sub(r"[^\w]+", "_", str(s).strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return "column"
    return "col_" + s if s[0].isdigit() else s


def _dedupe(names: list[str]) -> list[str]:
    seen: Counter = Counter()
    out = []
    for n in names:
        seen[n] += 1
        out.append(n if seen[n] == 1 else f"{n}_{seen[n]}")
    return out


def _blank_to_na(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s) or pd.api.types.is_bool_dtype(s):
        return s

    def f(v):
        if isinstance(v, str):
            t = v.strip()
            return None if t.lower() in MISSING_TOKENS else t
        return v

    return s.astype(object).map(f)


def _fix_header(df: pd.DataFrame) -> pd.DataFrame:
    """If the top rows are a title and the real header is lower down, promote it."""
    ncols = df.shape[1]
    if ncols == 0 or len(df) == 0:
        return df
    unnamed = sum(str(c).startswith("Unnamed:") for c in df.columns)
    if unnamed / ncols <= 0.5:
        return df
    for i in range(min(10, len(df))):
        row = df.iloc[i]
        vals = row.dropna()
        if len(vals) >= max(2, ncols * 0.5) and all(isinstance(v, str) for v in vals):
            out = df.iloc[i + 1:].copy()
            out.columns = [str(v).strip() if isinstance(v, str) else "column" for v in row]
            return out
    return df


def _tokens(name: str) -> set[str]:
    return set(name.split("_"))


def _f(s: pd.Series) -> pd.Series:
    return pd.Series(s.to_numpy(dtype="float64", na_value=np.nan), index=s.index)


def _numeric_result(name: str, s: pd.Series):
    nn = _f(s).dropna()
    if "date" in _tokens(name) and len(nn) and nn.between(20000, 80000).all() and (nn % 1 == 0).all():
        return pd.to_datetime(_f(s), unit="D", origin="1899-12-30"), "date"  # Excel serial dates
    if len(nn) and (nn % 1 == 0).all() and nn.abs().max() < 2**53:
        return _f(s).astype("Int64"), "integer"
    return _f(s), "float"


def _try_numeric(text: pd.Series):
    cleaned = text.str.replace(r"[\s,]", "", regex=True).str.replace(CUR_STRIP_RE, "", regex=True)
    cleaned = cleaned.str.replace(r"^\((.*)\)$", r"-\1", regex=True)  # (500) -> -500
    if cleaned.str.match(r"^[-+]?0\d").any():  # leading zeros -> a code, keep as text
        return None
    nums = pd.to_numeric(cleaned, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return nums if nums.notna().mean() >= 0.95 else None


def _try_date(text: pd.Series):
    if text.str.len().median() < 6:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            # ISO dates (2026-10-01) must NOT be read day-first, or 2026-10-01 becomes 10 January.
            iso = text.str.match(r"^\d{4}-\d{1,2}-\d{1,2}", na=False)
            dt = pd.Series(pd.NaT, index=text.index, dtype="datetime64[ns]")
            if iso.any():
                dt[iso] = pd.to_datetime(text[iso], errors="coerce", format="ISO8601").astype("datetime64[ns]")
            rest = ~iso & text.notna()
            if rest.any():
                dt[rest] = pd.to_datetime(text[rest], errors="coerce", dayfirst=True, format="mixed").astype("datetime64[ns]")
        except Exception:
            return None
    if not pd.api.types.is_datetime64_any_dtype(dt) or dt.notna().mean() < 0.95:
        return None
    return dt.dt.tz_localize(None) if getattr(dt.dt, "tz", None) is not None else dt


def infer_column(name: str, s: pd.Series):
    """Returns (clean_series, type_name, number_of_values_that_didnt_fit)."""
    nn = s.dropna()
    if nn.empty:
        return s.astype("string"), "empty", 0
    if pd.api.types.is_bool_dtype(s):
        return s.astype("boolean"), "boolean", 0
    if pd.api.types.is_datetime64_any_dtype(s):
        return s, "date", 0
    if pd.api.types.is_numeric_dtype(s):
        if _tokens(name) & TEXT_ONLY_TOKENS:  # SKUs, codes, ids are labels, not numbers to add up
            def as_label(v):
                return None if pd.isna(v) else (str(int(v)) if float(v).is_integer() else str(v))
            return s.map(as_label).astype("string"), "text", 0
        out, t = _numeric_result(name, s)
        return out, t, 0
    if all(isinstance(v, (bool, np.bool_)) for v in nn):
        return s.astype("boolean"), "boolean", 0
    if all(isinstance(v, (pd.Timestamp, __import__("datetime").datetime, __import__("datetime").date)) for v in nn):
        return pd.to_datetime(s), "date", 0

    text = nn.astype(str)
    if not (_tokens(name) & TEXT_ONLY_TOKENS):
        num = _try_numeric(text)
        if num is not None:
            full = pd.Series(np.nan, index=s.index)
            full.loc[num.index] = num
            out, t = _numeric_result(name, full)
            return out, t, int(num.isna().sum())
        dt = _try_date(text)
        if dt is not None:
            full = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
            full.loc[dt.index] = dt.astype("datetime64[ns]")
            return full, "date", int(dt.isna().sum())
    return s.astype("string"), "text", 0


# ------------------------------------------------------------------ profile pieces
def _fmt(v: float) -> str:
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def column_stats(s: pd.Series, typ: str) -> dict:
    n = len(s)
    miss = int(s.isna().sum())
    d = {"type": typ, "missing": miss, "missing_pct": round(100 * miss / n, 1) if n else 0.0,
         "distinct": int(s.nunique(dropna=True))}
    if typ in ("integer", "float"):
        nn = _f(s).dropna()
        d.update(min=float(nn.min()), max=float(nn.max()), mean=round(float(nn.mean()), 4), sum=round(float(nn.sum()), 4))
    elif typ == "date":
        d.update(min=s.min().strftime("%Y-%m-%d"), max=s.max().strftime("%Y-%m-%d"))
    return d


def describe_column(st: dict) -> str:
    t = st["type"]
    if t in ("integer", "float"):
        base = f"{'Whole' if t == 'integer' else 'Decimal'} numbers from {_fmt(st['min'])} to {_fmt(st['max'])}"
    elif t == "date":
        base = f"Dates from {st['min']} to {st['max']}"
    elif t == "text":
        base = f"Text with {st['distinct']} distinct values"
    elif t == "boolean":
        base = "True/false values"
    else:
        base = "Empty column"
    return base + (f"; {st['missing']} missing" if st["missing"] else "")


def map_fields(types: dict[str, str]) -> dict[str, str]:
    def ok(field, col):
        t = types[col]
        if field in NUMERIC_FIELDS:
            return t in ("integer", "float")
        if field == "date":
            return t == "date"
        return t in ("text", "integer")

    mapped: dict[str, str] = {}
    used: set[str] = set()
    for exact in (True, False):  # exact name match first, then whole-word-inside match
        for field, syns in FIELD_SYNONYMS.items():
            if field in mapped:
                continue
            for syn in syns:
                for col in types:
                    if col in used or not ok(field, col):
                        continue
                    if (col == syn) if exact else (f"_{syn}_" in f"_{col}_"):
                        mapped[field] = col
                        used.add(col)
                        break
                if field in mapped:
                    break
    return mapped


def compute_aggregates(df: pd.DataFrame, m: dict[str, str]) -> dict:
    agg: dict = {}
    key = m.get("product") or m.get("sku")
    if key:
        agg["product_count"] = int(df[key].nunique())
    q = m.get("quantity")
    if q:
        agg["total_quantity"] = float(_f(df[q]).sum())
        if m.get("unit_cost"):
            agg["total_value"] = float((_f(df[q]) * _f(df[m["unit_cost"]])).sum())
        if m.get("price"):
            agg["total_retail_value"] = float((_f(df[q]) * _f(df[m["price"]])).sum())
        if m.get("reorder_level"):
            both = pd.DataFrame({"q": _f(df[q]), "r": _f(df[m["reorder_level"]])}).dropna()
            # Rule used everywhere in Beaver: low stock means quantity <= reorder level.
            agg["low_stock_count"] = int((both["q"] <= both["r"]).sum())
    if m.get("date"):
        d = df[m["date"]].dropna()
        if len(d):
            agg["date_range"] = {"from": d.min().strftime("%Y-%m-%d"), "to": d.max().strftime("%Y-%m-%d")}
    return agg


def detect_currency(headers, raw: pd.DataFrame, fmt_symbols: list[str]):
    c: Counter = Counter()
    for h in headers:
        c.update(CUR_RE.findall(str(h)))
    for col in raw.columns:
        s = raw[col].dropna()
        if len(s) and not pd.api.types.is_numeric_dtype(s):
            for v in s.head(500).astype(str):
                c.update(CUR_RE.findall(v))
    c.update(fmt_symbols * 3 if fmt_symbols else [])
    codes = Counter()
    for sym, n in c.items():
        if sym in SYMBOL_TO_CODE:
            codes[SYMBOL_TO_CODE[sym]] += n
    return codes.most_common(1)[0][0] if codes else None


# ------------------------------------------------------------------ main entry
def parse_file(data: bytes, filename: str) -> list[ParsedSheet]:
    results: list[ParsedSheet] = []
    for sheet_name, raw, fmt_symbols in _read_tables(data, filename):
        if raw.shape[0] == 0 or raw.shape[1] == 0:
            continue
        df = raw.apply(_blank_to_na)
        df = df.dropna(how="all").dropna(axis=1, how="all")
        df = _fix_header(df)
        if df.shape[0] == 0 or df.shape[1] == 0:
            continue
        if len(df) > MAX_ROWS:
            raise ParseError(f"Sheet '{sheet_name}' has more than {MAX_ROWS:,} rows, which is too many for Beaver.")

        original = [str(c).strip() for c in df.columns]
        currency = detect_currency(original, df, fmt_symbols)
        names = _dedupe([normalize_name(c) for c in original])
        df.columns = names
        df = df.reset_index(drop=True)

        clean, columns, types, warns = {}, [], {}, []
        for orig, name in zip(original, names):
            series, typ, bad = infer_column(name, df[name])
            clean[name] = series
            types[name] = typ
            st = column_stats(series, typ)
            columns.append({"name": name, "original_name": orig, **st})
            if bad:
                warns.append(f"{bad} value(s) in '{orig}' weren't numbers/dates and were treated as missing.")
            if st["missing_pct"] >= 30 and typ != "empty":
                warns.append(f"'{orig}' is {st['missing_pct']}% empty.")
        clean_df = pd.DataFrame(clean)

        mapped = map_fields(types)
        for col in columns:
            col["mapped_to"] = next((f for f, c in mapped.items() if c == col["name"]), None)
            col["description"] = describe_column(col)

        profile = {
            "row_count": int(len(clean_df)),
            "column_count": len(columns),
            "columns": columns,
            "mapped_fields": mapped,
            "dictionary": {c["name"]: c["description"] for c in columns},
            "aggregates": compute_aggregates(clean_df, mapped),
            "currency": currency,
            "warnings": warns[:10],
        }
        results.append(ParsedSheet(name=sheet_name, df=clean_df, profile=profile))

    if not results:
        raise ParseError("We couldn't find any data in this file. Make sure the first row has column headings.")
    return results


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False, compression="snappy")
    return buf.getvalue()
