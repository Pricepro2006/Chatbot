# Master Deals Automation — Environment Setup & First‑Run Guide

Welcome! Follow this quick guide to get the **HP Inc. Master Deals** extractor + chatbot stack running on any fresh Windows (or macOS/Linux) machine.

---

## 0  Prerequisites

| Tool | Why it’s needed | Download |
|------|-----------------|----------|
| **Python 3.10 (or newer)** 64‑bit | All automation / Flask API | <https://www.python.org/downloads/> |
| **Git** *(optional)* | Clone the repo & pull updates | <https://git-scm.com/downloads> |
| **Microsoft C++ Build Tools**<br>(Windows only) | Required by the `pyarrow` wheel if a pre‑built binary isn’t available | <https://visualstudio.microsoft.com/visual-cpp-build-tools/> |
| **Pip ≥ 23** | Install Python packages | ships with Python; we’ll upgrade in the steps |

> **Heads‑up:** `pyarrow` is a large wheel (>50 MB) that provides high‑performance Parquet support. Most users will get a pre‑built wheel from PyPI; if not, C++ Build Tools will be used to compile it.

---

## 1  Clone / Download the project

```powershell
# Using Git (recommended):
cd "C:\Projects"   # or any folder you like
git clone https://github.com/YourOrg/master‑deals‑automation.git
cd master‑deals‑automation

# OR simply download the ZIP from GitHub › Extract it somewhere.
```

---

## 2  Create & activate a virtual environment

```powershell
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```
You should now see `(.venv)` in your terminal prompt.

---

## 3  Install dependencies (+auto‑install **pyarrow**)

### 3.1 One‑liner (preferred)

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
`requirements.txt` already lists:
```
pandas
openpyxl
pyarrow>=15.0.0   # Parquet engine
fastparquet       # optional second engine
flask
flask-cors
tqdm
```

### 3.2 Automatic fallback (built into the scripts)
If you skip the step above, **`Extract_and_table_v12.py`** (and any script that needs Parquet) will attempt to import `pyarrow` at runtime and, if it’s missing, run:
```python
subprocess.check_call([sys.executable, "-m", "pip", "install", "pyarrow>=15.0.0"])
```
That means the first execution may take a minute while the wheel is downloaded/compiled — but **no manual action is required**.

---

## 4  Initial data run (1‑time)

```powershell
# Move older versions from *Current Deals* to *Previous Deals*
python Move_Old_to_Previous_deals_v2.py

# Build / refresh master_deals.xlsx (keeps latest + previous version)
python Extract_and_table_v12.py
```
Both scripts will print `✅` on success. Any errors are written to `Master Files\Processing_Log.txt`.

---

## 5  Start the local chatbot API

```powershell
python local_bot_server_v3.7.4.py
```
Then open **chat_local.html** in a browser and interact with your data.

---

## 6  Daily usage pattern

1. Copy new `translate_quote_*.xlsx` files into **Current Deals**.
2. Run **Move_Old_to_Previous_deals_v2.py** to archive superseded versions.
3. Run **Extract_and_table_v12.py** to sync the master workbook.
4. Enjoy! 🥳

---

## 7  Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ImportError: No module named pyarrow` | Run `pip install pyarrow` **inside your activated venv**.<br>Or simply rerun the extractor — it will install automatically. |
| `fatal error: Python.h not found` on Windows | Install **Microsoft C++ Build Tools** (see prerequisites). |
| Parquet read/write is slow | Install both `pyarrow` **and** `fastparquet` — Pandas will pick the fastest backend automatically. |

---

## 8  Unattended installation (optional CI)

For CI / headless servers you can bootstrap everything with **one command**:
```bash
python - << "PY"
import subprocess, sys, textwrap, os
steps = textwrap.dedent("""
python -m venv .venv
. .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python Move_Old_to_Previous_deals_v2.py
python Extract_and_table_v12.py
""")
subprocess.run(steps, shell=True, check=True)
PY
```

---

> Need more help? Open an issue or ping the project chat — we’ve got you! 💬

