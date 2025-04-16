import sys
import os
import shutil
import pandas as pd
import re

# Force UTF-8 output to avoid encoding errors
sys.stdout.reconfigure(encoding='utf-8')

def split_deal(deal):
    if pd.isna(deal):
        return pd.Series([None, None])
    match = re.match(r"(\d+)\s*v\.(\d+)", str(deal).strip())
    if match:
        return pd.Series([match.group(1), int(match.group(2))])
    else:
        return pd.Series([None, None])

def main():
    try:
        # Step 1: Dynamic paths setup
        home_dir = os.path.expanduser('~')
        one_drive_base = os.path.join(home_dir, 'OneDrive - TDSYNNEX', 'HPI', 'Deal Repository')
        one_drive = os.path.join(home_dir, 'OneDrive - TDSYNNEX', 'HPI')

        folder_path = os.path.join(one_drive_base, 'Current Deals')
        current_folder_deals_file = os.path.join(one_drive_base, 'Current_Folder_Deals.xlsx')
        list_of_quotes_file = os.path.join(home_dir, 'OneDrive - TDSYNNEX', 'Downloads', 'list_of_quotes.xlsx')
        list_of_big_deals_file = os.path.join(one_drive, 'list_of_Big_deals_for_Insight.xlsx')

        print(f"Using folder path: {folder_path}")
        print(f"Will update list_of_quotes: {list_of_quotes_file}")
        print(f"Will update master Big Deals: {list_of_big_deals_file}")

        # Step 1.5: Check if list_of_quotes.xlsx exists, otherwise convert from .xls
        if not os.path.exists(list_of_quotes_file):
            list_of_quotes_xls = list_of_quotes_file.replace('.xlsx', '.xls')

            if os.path.exists(list_of_quotes_xls):
                print("list_of_quotes.xlsx not found, but list_of_quotes.xls found. Converting...")
                df_old_quotes = pd.read_excel(list_of_quotes_xls, skiprows=6, header=0)
                df_old_quotes = df_old_quotes.dropna(how='all')
                df_old_quotes = df_old_quotes.dropna(axis=1, how='all')
                if 'Deal' not in df_old_quotes.columns:
                    raise ValueError(f"'Deal' column not found after cleaning {list_of_quotes_xls}.")
                df_old_quotes.to_excel(list_of_quotes_file, index=False)
                print(f"Successfully converted and cleaned {list_of_quotes_xls} to {list_of_quotes_file}")
            else:
                print(f"Neither {list_of_quotes_file} nor {list_of_quotes_xls} were found. Creating an empty file...")
                empty_df = pd.DataFrame(columns=['Deal', 'Quote Base', 'Version'])
                empty_df.to_excel(list_of_quotes_file, index=False)
                print(f"Empty list_of_quotes.xlsx created at {list_of_quotes_file}")
        else:
            print("list_of_quotes.xlsx found and ready to process.")

        # Step 2: Read all files in the Current Deals folder
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"The folder {folder_path} does not exist.")

        file_list = os.listdir(folder_path)

        deals_data = []
        for filename in file_list:
            match = re.match(r'translate_quote_(\d+)_v(\d+)_all\.xlsx', filename)
            if match:
                quote_base = match.group(1)
                version = int(match.group(2))
                deal = f"{quote_base} v.{version}"
                deals_data.append({
                    'Deal': deal,
                    'Quote Base': quote_base,
                    'Version': version
                })

        # Step 3: Save Current_Folder_Deals.xlsx
        df_folder_deals = pd.DataFrame(deals_data)
        df_folder_deals.to_excel(current_folder_deals_file, index=False)
        print(f"Current folder deals saved to {current_folder_deals_file}")

        # Step 4: Read list_of_quotes.xlsx
        df_quotes = pd.read_excel(list_of_quotes_file, header=0)

        if 'Deal' not in df_quotes.columns:
            raise ValueError(f"'Deal' column not found in {list_of_quotes_file}.")

        # Step 5: Split Deal into Quote Base and Version
        df_quotes[['Quote Base', 'Version']] = df_quotes['Deal'].apply(split_deal)
        df_quotes = df_quotes.dropna(subset=['Quote Base', 'Version'])

        # Step 6: Prepare lookup
        folder_deals_lookup = df_folder_deals.set_index('Quote Base')['Version'].to_dict()

        # Step 7: Filter rows
        filtered_quotes = []
        for idx, row in df_quotes.iterrows():
            quote_base = row['Quote Base']
            version = row['Version']
            if quote_base in folder_deals_lookup:
                folder_version = folder_deals_lookup[quote_base]
                if version > folder_version:
                    filtered_quotes.append(row)
            else:
                filtered_quotes.append(row)

        df_filtered_quotes = pd.DataFrame(filtered_quotes)

        # Step 8: Reorder columns
        desired_order = [
            'Quote', 'Deal', 'Quote Base', 'Version', 'OPG',
            'Customer', 'Lead country', 'Date added',
            'Deal/Sellout begin date', 'Deal/Sellout end date'
        ]

        if 'Quote' not in df_filtered_quotes.columns:
            df_filtered_quotes['Quote'] = ''

        remaining_cols = [col for col in df_filtered_quotes.columns if col not in desired_order]
        final_columns = desired_order + remaining_cols
        existing_final_columns = [col for col in final_columns if col in df_filtered_quotes.columns]
        df_filtered_quotes = df_filtered_quotes[existing_final_columns]

        # Step 9: Save updated list_of_quotes.xlsx
        df_filtered_quotes.to_excel(list_of_quotes_file, index=False)
        print(f"Saved updated list_of_quotes.xlsx!")

        # Step 10: Update list_of_Big_deals_for_Insight.xlsx
        if os.path.exists(list_of_big_deals_file):
            df_big_deals = pd.read_excel(list_of_big_deals_file, skiprows=6)
            df_big_deals[['Quote Base', 'Version']] = df_big_deals['Deal'].apply(split_deal)
            big_deals_lookup = df_big_deals.set_index('Quote Base')

            updates_made = 0
            inserts_made = 0

            for idx, quote_row in df_filtered_quotes.iterrows():
                quote_base = quote_row['Quote Base']
                quote_version = quote_row['Version']

                if quote_base in big_deals_lookup.index:
                    existing_version = big_deals_lookup.loc[quote_base]['Version']
                    if quote_version > existing_version:
                        df_big_deals.loc[df_big_deals['Quote Base'] == quote_base, desired_order] = quote_row[desired_order].values
                        updates_made += 1
                else:
                    new_row = {col: quote_row.get(col, '') for col in df_big_deals.columns}
                    df_big_deals = pd.concat([df_big_deals, pd.DataFrame([new_row])], ignore_index=True)
                    inserts_made += 1

            df_big_deals.to_excel(list_of_big_deals_file, index=False, startrow=6)
            print(f"Updated master Big Deals file!")
            print(f"Total Updates: {updates_made}")
            print(f"Total Inserts: {inserts_made}")
        else:
            print(f"Big deals master file not found: {list_of_big_deals_file}")

    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    main()
