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

def load_master_deals(path: str = DATA_FILE) -> pd.DataFrame:
    if not Path(path).exists():
        log.warning("master_deals.xlsx not found – using empty dataframe")
        return pd.DataFrame(columns=REQUIRED_COLS)
    df = pd.read_excel(path)
    # ensure all required columns present
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = None
    df["DealBase"] = df["DealBase"].astype(str)
    # drop any accidentally imported header rows (where a cell equals its column name)
    # remove rows where DealBase repeats the header
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
    return re.findall(r"\b[A-Z0-9]{5,}(?:[/\-\s][A-Z0-9]{1,3})?\b", text.upper())

# ---------------------------------------------------------------------------

def find_fields(text: str) -> list[str]:
    # Now driven by LLM
    return get_fields(text)

# ---------------------------------------------------------------------------

def answer_remaining(deal: str, skus: list[str]) -> str:
    rows = DEALS_DF[DEALS_DF["DealBase"] == deal]
    if rows.empty:
        return f"Deal {deal} not found."
    parts = []
    series = rows["Product number"].astype(str).str.upper().fillna("")
    for sku in skus:
        base = fnorm.normalize_sku(sku)
        mask = series.str.startswith(base)
        sub = rows[mask]
        qty = int(sub.iloc[0]["Remaining qty"]) if not sub.empty else 0
        parts.append(f"{sku}: {qty} units remaining")
    return "; ".join(parts)


def answer_price(deal: str, skus: list[str]) -> str:
    rows = DEALS_DF[DEALS_DF["DealBase"] == deal]
    if rows.empty:
        return f"Deal {deal} not found."
    parts = []
    series = rows["Product number"].astype(str).str.upper().fillna("")
    for sku in skus:
        base = fnorm.normalize_sku(sku)
        mask = series.str.startswith(base)
        sub = rows[mask]
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
    parts = []
    series = rows["Product number"].astype(str).str.upper().fillna("")
    for sku in skus:
        base = fnorm.normalize_sku(sku)
        mask = series.str.startswith(base)
        sub = rows[mask]
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
    skus = extract_skus(q)
    fields = find_fields(q)
    if not deal:
        return jsonify({"answer": "Please specify a deal number."})

    answers = []
    for field in fields:
        handler = FIELD_ROUTER.get(fnorm.normalize_field_name(field))
        if handler:
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
