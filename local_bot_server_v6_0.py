#!/usr/bin/env python
# local_bot_server_v6_0.py – Flask API for Synonym-Brain v6.2
# ---------------------------------------------------------------------------
"""
A trimmed but functional successor to v5.0, updated to v6.2.

• Uses brain_loader_v5
• Re-uses field_normalizer_v6_0 helpers
• Provides /health & /ask endpoints
• Designed for Python 3.13, Flask 3.x
• Accepts --model argument for multi-model harness compatibility
"""
from __future__ import annotations
import sys
import logging
import re
from pathlib import Path
from datetime import datetime

import pandas as pd
from flask import Flask, request, jsonify
from llm_interface_v6_0 import get_fields

# ---------------------------------------------------------------------------
VERSION = "6.2.0"
START_TS = datetime.now()

# ---------------------------------------------------------------------------
# Import project helpers
try:
    from brain_loader_v5 import load_synonym_brain, add_synonym
except ImportError as e:
    print("❌ Could not import brain_loader_v5:", e)
    sys.exit(1)

try:
    import field_normalizer_v6_0 as fnorm
except ImportError as e:
    print("❌ Could not import field_normalizer_v6_0:", e)
    sys.exit(1)

# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bot_server_v6")

# ---------------------------------------------------------------------------
DATA_FILE = "master_deals.xlsx"
REQUIRED_COLS = [
    "DealBase", "Product number", "Customer",
    "End date", "Remaining qty", "Dealer net price \n[USD]", "Product family"
]

# ---------------------------------------------------------------------------
def load_master_deals(path: str = DATA_FILE) -> pd.DataFrame:
    if not Path(path).exists():
        log.warning("master_deals.xlsx not found – using empty dataframe")
        return pd.DataFrame(columns=REQUIRED_COLS)
    df = pd.read_excel(path)
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = None
    df["DealBase"] = df["DealBase"].astype(str)
    # Drop accidental header rows
    df = df[df["DealBase"].str.strip().str.lower() != "dealbase"]
    return df

DEALS_DF = load_master_deals()

# ---------------------------------------------------------------------------
BRAIN = load_synonym_brain()
log.info("Synonym brain loaded: %d entries", len(BRAIN))

# ---------------------------------------------------------------------------
def extract_deal(text: str) -> str | None:
    m = re.search(r"\b(\d{8})\b", text)
    return m.group(1) if m else None


def extract_skus(text: str) -> list[str]:
    # Only match alphanumeric sequences with at least one digit
    pattern = r"\b(?=[A-Z0-9]*\d)[A-Z0-9]{5,}(?:[/\-\s][A-Z0-9]{1,3})?\b"
    candidates = re.findall(pattern, text.upper())
    valid_bases = {
        fnorm.normalize_sku(s).upper()
        for s in DEALS_DF["Product number"].dropna().astype(str)
    }
    return [sku for sku in candidates if fnorm.normalize_sku(sku).upper() in valid_bases]

# ---------------------------------------------------------------------------
def find_fields(text: str) -> list[str]:
    # Primary field detection via LLM
    fields: list[str] = []
    try:
        raw = get_fields(text)
    except Exception as e:
        log.warning(f"LLM get_fields failed: {e}")
        raw = []
    for f in raw:
        can = fnorm.normalize_field_name(f)
        if can in FIELD_ROUTER and can not in fields:
            fields.append(can)
        # Fallback to static brain dictionary if LLM found nothing
    if not fields:
        tl = text.lower()
        for syn, fld in BRAIN.items():
            # match whole-word synonyms against text
            if fld in FIELD_ROUTER and re.search(r'' + re.escape(syn) + r'', tl):
                if fld not in fields:
                    fields.append(fld)
    return fields

# ---------------------------------------------------------------------------
def answer_remaining(deal: str, skus: list[str]) -> str:
    rows = DEALS_DF[DEALS_DF["DealBase"] == deal]
    if rows.empty:
        return f"Deal {deal} not found."
    series = rows["Product number"].astype(str).str.upper().fillna("")
    parts = []
    for sku in skus:
        base = fnorm.normalize_sku(sku)
        sub = rows[series.str.startswith(base)]
        qty = int(sub.iloc[0]["Remaining qty"]) if not sub.empty else 0
        parts.append(f"{sku}: {qty} units remaining")
    return "; ".join(parts)

def answer_price(deal: str, skus: list[str]) -> str:
    rows = DEALS_DF[DEALS_DF["DealBase"] == deal]
    if rows.empty:
        return f"Deal {deal} not found."
    series = rows["Product number"].astype(str).str.upper().fillna("")
    parts = []
    for sku in skus:
        base = fnorm.normalize_sku(sku)
        sub = rows[series.str.startswith(base)]
        price = float(sub.iloc[0]["Dealer net price \n[USD]"]) if not sub.empty else 0.0
        parts.append(f"{sku}: ${price:.2f}")
    return "; ".join(parts)

def answer_customer(deal: str, skus: list[str]) -> str:
    rows = DEALS_DF[DEALS_DF["DealBase"] == deal]
    cust = rows.iloc[0]["Customer"] if not rows.empty else "Unknown"
    return f"Customer: {cust}"

def answer_family(deal: str, skus: list[str]) -> str:
    rows = DEALS_DF[DEALS_DF["DealBase"] == deal]
    if rows.empty:
        return f"Deal {deal} not found."
    series = rows["Product number"].astype(str).str.upper().fillna("")
    parts = []
    for sku in skus:
        base = fnorm.normalize_sku(sku)
        sub = rows[series.str.startswith(base)]
        fam = sub.iloc[0]["Product family"] if not sub.empty else "Unknown"
        parts.append(f"{sku}: {fam}")
    return "; ".join(parts)

def answer_enddate(deal: str, skus: list[str]) -> str:
    rows = DEALS_DF[DEALS_DF["DealBase"] == deal]
    dt = rows.iloc[0]["End date"] if not rows.empty else None
    return f"End date: {pd.to_datetime(dt).date() if dt else 'Unknown'}"

FIELD_ROUTER = {
    "Remaining qty": answer_remaining,
    "Dealer net price \n[USD]": answer_price,
    "Customer": answer_customer,
    "Product family": answer_family,
    "End date": answer_enddate,
}

# ---------------------------------------------------------------------------
app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": VERSION,
        "brain_size": len(BRAIN),
        "deals_loaded": len(DEALS_DF),
        "uptime_s": (datetime.now() - START_TS).total_seconds()
    })

@app.route("/ask", methods=["POST"])
def ask():
    q = request.json.get("question", "")
    if not q:
        return jsonify({"answer": "No question provided."})
    deal = extract_deal(q)
    if not deal:
        return jsonify({"answer": "Please specify a deal number."})
    # detect fields (LLM + static fallback)
    raw_fields = []
    try:
        raw_fields = get_fields(q)
    except Exception:
        raw_fields = []
    fields: list[str] = find_fields(q)
    for raw in raw_fields:
        can = fnorm.normalize_field_name(raw)
        if can in FIELD_ROUTER:
            try:
                add_synonym(raw, can)
            except Exception:
                pass
            fields.append(can)
    if not fields:
        return jsonify({"answer": "Sorry, I couldn't determine which field you're asking for."})
    skus = extract_skus(q)
    # For fields requiring a SKU, if none was extracted, prompt the user
    sku_required = {f for f in FIELD_ROUTER if f not in {"Customer", "End date"}}
    if any(field in sku_required for field in fields) and not skus:
        return jsonify({"answer": "Please specify which product number you are asking about for your query."})
    answers: list[str] = []
    for field in fields:
        handler = FIELD_ROUTER[field]
        try:
            answers.append(handler(deal, skus))
        except Exception as e:
            log.error(f"Handler {field} failed: {e}")
    return jsonify({"answer": "\n".join(answers)})

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--model", type=str, default=None,
                    help="Model name for harness compatibility")
    args = ap.parse_args()
    if args.model:
        log.info("Starting server with model override: %s", args.model)
    app.run(host="0.0.0.0", port=args.port, debug=args.debug, threaded=True)
