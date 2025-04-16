
from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import re
import os
import csv
from datetime import datetime
from brain_loader import load_synonym_brain, find_backend_field_from_question
from llm_interface import infer_intent

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
MASTER_FILE_PATH = "master_deals.xlsx"
BRAIN_FILE = "variable_names.xlsx"

# Load Excel data
if os.path.exists(MASTER_FILE_PATH):
    deals_df = pd.read_excel(MASTER_FILE_PATH, sheet_name="Deals", engine="openpyxl")
else:
    deals_df = pd.DataFrame()

synonym_brain = load_synonym_brain(BRAIN_FILE)

# --- Logging Functions ---
def log_question(question, intent, action, result_status):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('questions_log.csv', 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([timestamp, question, intent, action, result_status])

def log_unanswered(question):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('unanswered_log.csv', 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([timestamp, question])

def log_llm_inference(question, inferred_action):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('llm_inferred_log.csv', 'a', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow([timestamp, question, inferred_action])

# --- Utility Functions ---
def extract_deal_id(text):
    match = re.search(r'\b\d{8}\b', text)
    return match.group(0) if match else ''

def extract_skus(text):
    text = text.lower()
    return re.findall(r'\b(?=.*[a-zA-Z])(?=.*\d)[\w#-]{5,12}\b', text)

def extract_quantity(text):
    match = re.search(r'(?:qty|quantity|remaining|less than)?\D*(\d{1,5})', text.lower())
    return int(match.group(1)) if match else None

@app.route('/', methods=['GET'])
def index():
    return jsonify({"status": "✅ Chatbot v3 is running."})

@app.route('/ask', methods=['POST'])
def ask():
    try:
        data = request.get_json()
        question = data.get('question', '')
        deal_id = data.get('deal_id', '')

        # Try extracting deal_id if not provided explicitly
        if not deal_id:
            deal_id = extract_deal_id(question)
            if deal_id:
                question = question.replace(deal_id, '').strip()

        # Extract SKU(s) and optional quantity threshold
        skus = extract_skus(question)
        qty_threshold = extract_quantity(question)

        backend_field = find_backend_field_from_question(question, synonym_brain)
        if backend_field == "unknown":
            inferred = infer_intent(question)
            if inferred in synonym_brain.values():
                backend_field = inferred
                log_llm_inference(question, inferred)
            else:
                log_question(question, "unknown", "none", "fail")
                log_unanswered(question)
                return jsonify({"answer": "❌ Sorry, I couldn't understand your question."})

        if deal_id:
            deal_filtered = deals_df[deals_df['DealBase'].astype(str).str.lower() == deal_id.lower()]
            if deal_filtered.empty:
                return jsonify({"answer": f"❌ No matching Deal ID {deal_id} found."})
        else:
            return jsonify({"answer": "❌ Please include or reference a valid dealbase (8-digit number)."})

        # SKU-based responses
        results = []
        for sku in skus:
            sku_base = sku.split('#')[0]
            product_column = deal_filtered['Product number'].astype(str).str.lower()
            matched = deal_filtered[
                (product_column == sku) |
                (product_column.str.split('#').str[0] == sku_base)
            ]

            if matched.empty:
                results.append(f"❌ SKU {sku} not found under Deal {deal_id}.")
            else:
                if qty_threshold and 'Remaining qty' in matched.columns:
                    matched = matched[matched['Remaining qty'].fillna(999999).astype(int) < qty_threshold]

                if matched.empty:
                    results.append(f"✅ No SKUs with qty < {qty_threshold} for {sku} under Deal {deal_id}.")
                else:
                    value = matched.iloc[0].get(backend_field, "Not Available")
                    results.append(f"✅ {backend_field} for {sku}: {value}")

        log_question(question, backend_field, "multi_lookup", "success")
        return jsonify({"answer": "<br>".join(results)})

    except Exception as e:
        log_question("internal_error", "error", "server_crash", "fail")
        return jsonify({"answer": f"❌ Internal server error: {str(e)}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
