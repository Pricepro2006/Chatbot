# local_bot_server_v2.8.py (Admin Panel Upgrade with Multi-SKU Detection and Group Deal Scan + SKU Base Normalization)

from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_cors import CORS
import pandas as pd
import os
import csv
from datetime import datetime
from werkzeug.utils import secure_filename
from brain_loader import load_synonym_brain, find_backend_field_from_question
from llm_interface import infer_intent
import re

from PIL import Image
import pytesseract
import tempfile
app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
MASTER_FILE_PATH = "master_deals.xlsx"
ADMIN_UPLOAD_FOLDER = "Admin Uploads"
BRAIN_FILE = "variable_names.xlsx"

os.makedirs(ADMIN_UPLOAD_FOLDER, exist_ok=True)

deals_df = pd.read_excel(MASTER_FILE_PATH, sheet_name="Deals", engine="openpyxl")
bundles_df = pd.read_excel(MASTER_FILE_PATH, sheet_name="Bundles", engine="openpyxl")
synonym_brain = load_synonym_brain(BRAIN_FILE)

# --- Logging ---
def log_question(question, intent, action, result_status):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('questions_log.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, question, intent, action, result_status])

def log_unanswered(question):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('unanswered_log.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, question])

def log_llm_inference(question, inferred_action):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('llm_inferred_log.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, question, inferred_action])

# --- SKU Extraction ---
def extract_skus_from_question(question_text):
    text = question_text.lower()
    skus = re.findall(r'\b(?=.*[a-zA-Z])(?=.*\d)[\w#-]{5,12}\b', text)
    return [sku.strip().lower() for sku in skus if sku.strip()]

# --- Flask Routes ---
@app.route('/', methods=['GET'])
def index():
    return jsonify({"status": "✅ Local Bot Server v2.8 running!"}), 200

@app.route('/ask', methods=['POST'])
def ask():
    try:
        data = request.get_json()
        question = data.get('question', '')
        deal_id = data.get('deal_id', '')

        if not question or not deal_id:
            log_question(question, "missing", "none", "fail")
            return jsonify({"answer": "❌ Missing question or Deal ID. Please provide both."}), 200

        backend_field = find_backend_field_from_question(question, synonym_brain)

        if backend_field == "unknown":
            inferred_action = infer_intent(question)
            if inferred_action in synonym_brain.values():
                backend_field = inferred_action
                log_llm_inference(question, inferred_action)
            else:
                log_question(question, "unknown", "none", "fail")
                log_unanswered(question)
                return jsonify({"answer": "❌ Sorry, I couldn't understand your question yet."}), 200

        deal_filtered = deals_df[
            deals_df['DealBase'].astype(str).str.lower() == deal_id.lower()
        ]

        if deal_filtered.empty:
            return jsonify({"answer": f"❌ No matching Deal ID {deal_id} found."}), 200

        skus = extract_skus_from_question(question)

        if not skus:
            if 'remaining qty' in question.lower():
                numbers = re.findall(r'\d+', question)
                threshold = int(numbers[0]) if numbers else 10

                results = deal_filtered[
                    deal_filtered['Remaining qty'].fillna(99999).astype(int) < threshold
                ]

                sku_list = results['Product number'].tolist()
                count = len(sku_list)

                if count == 0:
                    return jsonify({"answer": f"✅ No SKUs under Deal {deal_id} with Remaining qty < {threshold}."}), 200
                else:
                    skus_string = ', '.join(sku_list)
                    return jsonify({"answer": f"✅ {count} SKUs under Deal {deal_id} with Remaining qty < {threshold}: {skus_string}"}), 200

            log_question(question, backend_field, "extract_sku", "fail")
            log_unanswered(question)
            return jsonify({"answer": "❌ Could not find SKU / Part Number in your question."}), 200

        results = []
        product_column = deal_filtered['Product number'].astype(str).str.lower()
        for sku in skus:
            sku_base = sku.split('#')[0]
            matched = deal_filtered[
                (product_column == sku) |
                (product_column.str.split('#').str[0] == sku_base)
            ]
            if matched.empty:
                results.append(f"❌ SKU {sku} not found under Deal {deal_id}.")
            else:
                value = matched.iloc[0].get(backend_field, "Not Available")
                if pd.isna(value) or value == "":
                    results.append(f"❌ {backend_field} not available for SKU {sku}.")
                else:
                    results.append(f"✅ {backend_field} for SKU {sku}: {value}")

        log_question(question, backend_field, "multi_lookup", "success")
        return jsonify({"answer": "<br>".join(results)}), 200

    except Exception as e:
        log_question("internal_error", "error", "server_crash", "fail")
        return jsonify({"answer": f"❌ Internal server error: {str(e)}"}), 200


@app.route('/admin', methods=['GET'])
def admin_panel():
    df = pd.read_excel(BRAIN_FILE)
    table_html = "<table border='1'><tr><th>Main Field</th>"
    max_cols = df.shape[1]
    for i in range(1, max_cols):
        table_html += f"<th>Synonym {i}</th>"
    table_html += "</tr>"

    for _, row in df.iterrows():
        table_html += "<tr>"
        for i in range(max_cols):
            val = row[i] if i < len(row) else ""
            val = "" if pd.isna(val) else str(val)
            table_html += f"<td contenteditable='true'>{val}</td>"
        table_html += "</tr>"
    table_html += "</table>"

    html = f'''
    <html><head><title>Admin Brain Editor</title></head>
    <body>
    <h1>🧠 Live Synonym Editor</h1>
    <p>Edit cells directly. Click SAVE when done.</p>
    <div id='editableTable'>{table_html}</div>
    <button onclick='saveTable()'>Save</button>
    <form action='/reload_brain' method='get'><button type='submit'>Reload Brain</button></form>
    <script>
    function saveTable() {{
      const table = document.querySelector("#editableTable table");
      const rows = table.querySelectorAll("tr");
      const data = [];
      for (let i = 1; i < rows.length; i++) {{
        const cells = rows[i].querySelectorAll("td");
        const row = [];
        cells.forEach(cell => row.push(cell.innerText.trim()));
        data.push(row);
      }}
      fetch('/save_brain', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ data: data }})
      }}).then(resp => resp.text()).then(msg => alert(msg));
    }}
    </script>
    </body></html>
    '''
    return render_template_string(html)

@app.route('/save_brain', methods=['POST'])
def save_brain():
    content = request.get_json()
    rows = content.get('data', [])
    max_cols = max(len(row) for row in rows)
    for row in rows:
        while len(row) < max_cols:
            row.append('')
    df = pd.DataFrame(rows)
    df.to_excel(BRAIN_FILE, index=False)
    return "✅ Brain saved! Go back and reload brain if needed."
if __name__ == '__main__':
    context = ('cert.pem', 'key.pem')
    app.run(host='0.0.0.0', port=5000, ssl_context=context)
