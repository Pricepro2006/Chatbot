#!/usr/bin/env python
# field_normalizer_v6_0.py – shared helpers for Synonym‑Brain 6.x
# ---------------------------------------------------------------------------
"""
• Canonical field name mapping and utilities
• SKU normalisation (preserve original format optional)
• Response format standardisers reused by test harness

This is an incremental lift from v4.2, tweaked for Python 3.13.
"""

from __future__ import annotations
import re

VERSION = "6.0.0"

# ---------------------------------------------------------------------------
CANONICAL_MAP = {
    "dealer net price [usd]": "Dealer net price \n[USD]",
    "dealer net price":       "Dealer net price \n[USD]",
    "dealer price":           "Dealer net price \n[USD]",
    "price":                  "Dealer net price \n[USD]",
    "cost":                   "Dealer net price \n[USD]",
    "end date":               "End date",
    "expiration date":        "End date",
    "product family":         "Product family",
    "family":                 "Product family",
    "remaining qty":          "Remaining qty",
    "quantity":               "Remaining qty",
    "stock":                  "Remaining qty",
    "customer":               "Customer",
    "client":                 "Customer",
}

# ---------------------------------------------------------------------------
def normalize_field_name(field: str) -> str:
    if not field:
        return field
    f = re.sub(r'\s+', ' ', field.lower()).strip()
    return CANONICAL_MAP.get(f, field)

def normalize_sku(sku: str, keep_format: bool = False) -> str:
    if not isinstance(sku, str):
        sku = str(sku)
    if keep_format:
        return sku.strip().upper()
    # drop after slash, dash or space
    return re.split(r'[\/\-\s]', sku.strip().upper())[0]

# Standardisers used by tests to avoid whitespace / decimal mismatches
def std_qty(txt: str) -> str:
    return re.sub(r'(\d+)\s*(?:units?|pcs?|pieces?)?\s*(?:remaining)?',
                  lambda m: f"{m.group(1)} units remaining", txt, flags=re.I)

def std_price(txt: str) -> str:
    return re.sub(r'\$\s*([0-9]+\.\d{1,4})',
                  lambda m: f"${float(m.group(1)):.2f}", txt)

def std_date(txt: str) -> str:
    return re.sub(r'(\d{4}-\d{2}-\d{2}).*', r'\1', txt)

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("field_normalizer_v6_0", VERSION)
    tests = ["price", "Dealer Net Price [usd]", "quantity", "Customer"]
    for t in tests:
        print(t, "->", normalize_field_name(t))
    print("SKU:", normalize_sku("A1B2C3 / ABA"))
