# brain_loader.py

import pandas as pd

def load_synonym_brain(filepath):
    brain = {}
    try:
        df = pd.read_excel(filepath, sheet_name=0)

        for index, row in df.iterrows():
            main_field = str(row.iloc[0]).strip()
            if pd.isna(main_field) or main_field.lower() == 'nan':
                continue
            for variation in row[1:]:
                if pd.isna(variation):
                    continue
                brain[str(variation).strip().lower()] = main_field

    except Exception as e:
        print(f"❌ Failed to load brain: {e}")
    return brain


def find_backend_field_from_question(question_text, synonym_brain):
    q = question_text.lower()

    for synonym, real_field in synonym_brain.items():
        if synonym in q:
            return real_field

    return "unknown"


# --- Example Test Run ---
if __name__ == "__main__":
    brain = load_synonym_brain("variable_names.xlsx")
    test_question = "How much does this part cost?"
    print(find_backend_field_from_question(test_question, brain))