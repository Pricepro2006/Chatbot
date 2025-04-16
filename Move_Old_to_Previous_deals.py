import os
import re
import shutil

# Dynamically get the user's folder
user_folder = os.environ['USERPROFILE']

# Define your source and destination folders
source_folder = os.path.join(user_folder, "OneDrive - TDSYNNEX", "HPI", "Deal Repository", "Current Deals")
destination_folder = os.path.join(user_folder, "OneDrive - TDSYNNEX", "HPI", "Deal Repository", "Previous Deals")

# Make sure destination folder exists
os.makedirs(destination_folder, exist_ok=True)

# Regex to match filenames
pattern = re.compile(r'(translate_quote_\d+)_v(\d+)_all\.xlsx', re.IGNORECASE)

# Dictionary to keep track of latest versions in Current Deals
latest_versions = {}

# First pass: collect the latest version for each quote in Current Deals
for filename in os.listdir(source_folder):
    match = pattern.match(filename)
    if match:
        base_name = match.group(1)
        version = int(match.group(2))

        if base_name not in latest_versions:
            latest_versions[base_name] = (version, filename)
        else:
            if version > latest_versions[base_name][0]:
                latest_versions[base_name] = (version, filename)

# Second pass: collect older versions to move
files_to_move = []

for filename in os.listdir(source_folder):
    match = pattern.match(filename)
    if match:
        base_name = match.group(1)
        version = int(match.group(2))
        latest_version, latest_file = latest_versions[base_name]

        if version < latest_version:
            files_to_move.append(filename)

# Now move them safely
for filename in files_to_move:
    source_path = os.path.join(source_folder, filename)
    dest_path = os.path.join(destination_folder, filename)
    print(f"Moving {filename} to Previous Deals...")
    shutil.move(source_path, dest_path)

# Third pass: clean up Previous Deals to keep only the highest version per base name
previous_versions = {}

# Collect highest version per base name in Previous Deals
for filename in os.listdir(destination_folder):
    match = pattern.match(filename)
    if match:
        base_name = match.group(1)
        version = int(match.group(2))

        if base_name not in previous_versions:
            previous_versions[base_name] = (version, filename)
        else:
            if version > previous_versions[base_name][0]:
                previous_versions[base_name] = (version, filename)

# Delete older versions in Previous Deals
for filename in os.listdir(destination_folder):
    match = pattern.match(filename)
    if match:
        base_name = match.group(1)
        version = int(match.group(2))
        highest_version, highest_version_file = previous_versions[base_name]

        if version < highest_version:
            file_to_delete = os.path.join(destination_folder, filename)
            print(f"Deleting older version {filename} from Previous Deals...")
            os.remove(file_to_delete)

print("Done!")
