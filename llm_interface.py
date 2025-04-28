"""llm_interface_v6_0.py – Unified LLM gateway (Ollama)
Updated: 2025‑04‑24

Changes from v5.1.0
-------------------
* Per‑model cold‑start timeout (Mixtral much slower to page into RAM)
* Automatic one‑time "ping" warm‑up so the next real call is instant
* Default timeout raised to 60 s (can always be overridden)
* Public API (`get_mistral_suggestion`, `get_fields`) unchanged → no edits
  required in the rest of the project.
"""
from __future__ import annotations

import json, logging, re, requests
from typing import List, Dict

logger = logging.getLogger(__name__)
logger.addHandler(logging.FileHandler("llm_interface_v6.log", encoding="utf‑8"))
logger.setLevel(logging.INFO)

VERSION = "6.0.1"
OLLAMA_API = "http://localhost:11434/api/generate"

# ---------------------------------------------------------------------------
#  Model registry – you can add more Ollama tags here
# ---------------------------------------------------------------------------
MODEL_CONFIG: Dict[str, Dict] = {
    "mistral": {
        "name": "mistral",       # ollama tag
        "context_length": 8192,
        "preferred_for": ["short", "simple"],
        "cold_start_timeout": 30,  # seconds
    },
    "openchat": {
        "name": "openchat",
        "context_length": 8192,
        "preferred_for": ["conversational"],
        "cold_start_timeout": 30,
    },
    "mixtral": {
        "name": "mixtral",
        "context_length": 32768,
        "preferred_for": ["complex", "nuanced"],
        "cold_start_timeout": 90,   # bigger model – empirically 2‑3× slower
    },
}
DEFAULT_MODEL = "mistral"

# Simple prompt templates (unchanged)
PROMPT_TEMPLATES: Dict[str, str] = {
    "mistral": (
        "You are a synonym‑suggestion assistant. The user will give a natural "
        "language question and you must return a JSON list of matching field "
        "names. Return only these exact field names:\n"
        "- \"Remaining qty\"\n- \"Dealer net price [USD]\"\n- \"Customer\"\n"
        "- \"Product family\"\n- \"End date\"\n\nQuestion:\n\"{question}\""
    ),
    "openchat": (
        "Determine which fields the user is asking about in: \"{question}\"\n"
        "Return a JSON list, using exactly these field names: Remaining qty, Dealer net price [USD], Customer, Product family, End date."
    ),
    "mixtral": (
        "Identify the fields referenced in the question (JSON array of objects with field + confidence 0‑100). Fields: Remaining qty, Dealer net price [USD], Customer, Product family, End date.\n\nQuestion: {question}"
    ),
}

# ---------------------------------------------------------------------------
#  Warm‑up helpers
# ---------------------------------------------------------------------------
_warmed_models: set[str] = set()

def _warm_up_model(model: str) -> None:
    """Ping the model once so subsequent calls are fast."""
    if model in _warmed_models:
        return
    timeout = MODEL_CONFIG.get(model, {}).get("cold_start_timeout", 60)
    try:
        requests.post(
            OLLAMA_API,
            json={"model": model, "prompt": "ping", "stream": False},
            timeout=timeout,
        )
        _warmed_models.add(model)
        logger.debug("Warmed model %s", model)
    except requests.exceptions.RequestException as exc:
        logger.warning("Warm‑up for %s failed: %s", model, exc)

# ---------------------------------------------------------------------------
#  Core call
# ---------------------------------------------------------------------------

def get_mistral_suggestion(question: str, model_name: str | None = None, *, timeout: int = 60) -> List[str]:
    """Return a list of canonical fields suggested by the LLM."""
    if not question:
        return []

    model_name = (model_name or DEFAULT_MODEL).lower()
    if model_name not in MODEL_CONFIG:
        logger.warning("Unknown model %s – falling back to %s", model_name, DEFAULT_MODEL)
        model_name = DEFAULT_MODEL

    # Cold‑start warm‑up
    _warm_up_model(model_name)

    prompt = PROMPT_TEMPLATES.get(model_name, PROMPT_TEMPLATES[DEFAULT_MODEL]).format(question=question)

    try:
        r = requests.post(
            OLLAMA_API,
            json={"model": MODEL_CONFIG[model_name]["name"], "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        r.raise_for_status()
        raw = r.json().get("response", "")
    except requests.exceptions.RequestException as exc:
        logger.error("LLM call failed (%s): %s", model_name, exc)
        return []

    # Extract JSON array
    match = re.search(r"\[(.*?)\]", raw, re.DOTALL)
    if not match:
        # fall‑back: grab quoted strings
        return re.findall(r'"([^"\]]+)"', raw)

    snippet = "[" + match.group(1) + "]"
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError:
        # if we expected array of objects (mixtral)
        if model_name == "mixtral":
            return re.findall(r"\"field\"\\s*:\\s*\"([^\"]+)\"", snippet)
        return re.findall(r'"([^"\]]+)"', snippet)

    if isinstance(data, list):
        # Flatten list if it’s list[str] or list[dict]
        if data and isinstance(data[0], dict):
            # keep only fields with confidence ≥70 if present
            return [item["field"] for item in data if item.get("confidence", 0) >= 70]
        return [str(x) for x in data]
    return []

# ---------------------------------------------------------------------------
#  High‑level convenience
# ---------------------------------------------------------------------------

def _auto_model(query: str) -> str:
    """Quick rules – use mixtral for long/complex queries, openchat for conversational, else mistral."""
    q = query.lower()
    if any(k in q for k in (" and ", " with ", " including ")):
        return "mixtral"
    if any(k in q for k in ("could you", "would you", "please", "thank")):
        return "openchat"
    return "mistral"

def get_fields(query: str, model_name: str | None = None, *, timeout: int = 60) -> List[str]:
    model = model_name or _auto_model(query)
    return get_mistral_suggestion(query, model, timeout=timeout)

# ---------------------------------------------------------------------------
#  CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"LLM interface {VERSION}")
    example = "What's the remaining qty for SKU123 in deal 12345678?"
    print("Query:", example)
    print("Detected fields:", get_fields(example))
