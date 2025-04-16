# llm_interface.py — Enhanced with Fallback Synonym Detection via Mistral 7B + Logging + Auto-Apply

import requests
import json
import csv
import os
import pandas as pd

OLLAMA_HOST = "http://localhost:11434"
MODEL = "mistral"
LEARNING_LOG = "learned_synonyms.csv"
BRAIN_FILE = "variable_names.xlsx"

# -- Log new fallback synonym pairs to CSV
def log_fallback_synonym(question, field):
    try:
        with open(LEARNING_LOG, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([question.strip(), field.strip()])
    except Exception as e:
        pass  # Do not crash on logging failure

# -- Load brain fields and generate prompt for field mapping
def infer_intent(user_question):
    try:
        from brain_loader import load_synonym_brain
        brain = load_synonym_brain(BRAIN_FILE)
        known_fields = sorted(set(brain.values()))

        field_prompt = f"""
You are a field-matching assistant. Given a user's question, respond with the best matching field from this list:

{', '.join(known_fields)}

Only reply with the exact field name, no explanation.

Question: "{user_question}"
"""

        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"model": MODEL, "prompt": field_prompt, "stream": False})
        )
        if response.status_code == 200:
            parsed = response.json()
            guessed_field = parsed.get("response", "").strip()
            if guessed_field in known_fields:
                log_fallback_synonym(user_question, guessed_field)
                return guessed_field
        return "unknown"
    except Exception:
        return "unknown"

# -- Apply learned synonyms directly into variable_names.xlsx
def apply_learned_synonyms():
    try:
        if not os.path.exists(LEARNING_LOG) or not os.path.exists(BRAIN_FILE):
            return

        df_log = pd.read_csv(LEARNING_LOG, names=["Synonym", "Field"])
        df_log.drop_duplicates(inplace=True)

        # Load brain file
        brain_df = pd.read_excel(BRAIN_FILE, sheet_name=0)
        brain_dict = {}
        for _, row in brain_df.iterrows():
            field = str(row[0]).strip()
            for val in row[1:]:
                if pd.notna(val):
                    brain_dict[str(val).strip().lower()] = field

        new_rows = []
        for _, row in df_log.iterrows():
            syn = str(row["Synonym"]).strip()
            field = str(row["Field"]).strip()
            if syn.lower() not in brain_dict:
                new_rows.append((field, syn))

        if new_rows:
            for field in sorted(set(r[0] for r in new_rows)):
                existing_row = brain_df[brain_df.iloc[:, 0] == field]
                if not existing_row.empty:
                    index = existing_row.index[0]
                    existing_values = set(str(v).strip().lower() for v in brain_df.loc[index, 1:].values if pd.notna(v))
                    additions = [r[1] for r in new_rows if r[0] == field and r[1].lower() not in existing_values]
                    for add in additions:
                        for i in range(1, len(brain_df.columns)):
                            if pd.isna(brain_df.iloc[index, i]):
                                brain_df.iat[index, i] = add
                                break
                else:
                    pads = [""] * (len(brain_df.columns) - 2)
                    synonyms = [r[1] for r in new_rows if r[0] == field]
                    brain_df.loc[len(brain_df)] = [field] + synonyms + pads

            brain_df.to_excel(BRAIN_FILE, index=False)
            print("✅ Brain file updated with new synonyms.")

    except Exception as e:
        print(f"❌ Failed to apply learned synonyms: {e}")
