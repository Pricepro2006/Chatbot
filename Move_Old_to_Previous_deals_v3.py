# Move_Old_to_Previous_deals_v3.py — resilient & configurable
"""
Fixes & improvements over v2
---------------------------
1. **Robust filename parsing** – accepts optional text after the version (e.g. "_all"),
   optional capitalisation, and safeguards against malformed names.
2. **Configurable keep‑count** – default keeps only the **latest** version per deal, but
   you can pass `--keep 2` (or any N) to hold more versions in *Current Deals*.
3. **Dry‑run mode** – add `--dry-run` to preview the moves/deletes without touching files.
4. **Cross‑platform paths & clearer logging** – uses *pathlib* + `logging` to both console
   and `move_old_log.txt`.

Usage examples
--------------
```bash
python Move_Old_to_Previous_deals_v3.py          # keep 1 latest; real move
python Move_Old_to_Previous_deals_v3.py --keep 2 # keep 2 latest versions
python Move_Old_to_Previous_deals_v3.py --dry-run
```
"""
from __future__ import annotations
import re, argparse, logging
from pathlib import Path
from typing import Dict, List
import shutil

BASE   = Path.home() / 'OneDrive - TDSYNNEX' / 'HPI' / 'Deal Repository'
CURDIR = BASE / 'Current Deals'
PREVDIR= BASE / 'Previous Deals'
LOGFILE= BASE / 'move_old_log.txt'

# ----------------------------------------------------------------------------
# logging setup
LOGFORMAT = '%(asctime)s %(levelname)s %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=LOGFORMAT,
    handlers=[
        logging.FileHandler(LOGFILE, mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ----------------------------------------------------------------------------
# filename pattern (case‑insensitive)
PAT = re.compile(r'(translate_quote_\d{6,})_v(\d+)(?:_[^.]*)?\.xlsx$', re.IGNORECASE)

# ----------------------------------------------------------------------------

def group_by_latest(files: List[Path]) -> Dict[str, int]:
    """Return mapping of deal base ➔ highest version number found."""
    latest: Dict[str, int] = {}
    for f in files:
        m = PAT.match(f.name)
        if not m:
            continue
        base, ver = m.group(1).lower(), int(m.group(2))
        latest[base] = max(ver, latest.get(base, 0))
    return latest


def select_keep_versions(files: List[Path], keep: int) -> Dict[str, List[int]]:
    """For each deal base, return the *keep* highest versions present."""
    versions: Dict[str, List[int]] = {}
    for f in files:
        m = PAT.match(f.name)
        if not m:
            continue
        base, ver = m.group(1).lower(), int(m.group(2))
        versions.setdefault(base, []).append(ver)
    # sort & slice
    return {b: sorted(vs, reverse=True)[:keep] for b, vs in versions.items()}


def move_old(args):
    CURDIR.mkdir(parents=True, exist_ok=True)
    PREVDIR.mkdir(parents=True, exist_ok=True)

    src_files = [f for f in CURDIR.iterdir() if f.is_file() and PAT.match(f.name)]
    keep_versions = select_keep_versions(src_files, args.keep)

    # First pass – move older than *keep* to Previous Deals
    for f in src_files:
        m = PAT.match(f.name)
        if not m:
            continue
        base, ver = m.group(1).lower(), int(m.group(2))
        if ver not in keep_versions[base]:
            dest = PREVDIR / f.name
            logging.info(f"MOVE   {f.name}  ➜  Previous Deals")
            if not args.dry_run:
                try:
                    shutil.move(str(f), str(dest))
                except shutil.Error:  # dest exists
                    dest.unlink()
                    shutil.move(str(f), str(dest))

    # Second pass – inside Previous Deals keep only 1 highest version (cleanup)
    prev_files = [f for f in PREVDIR.iterdir() if f.is_file() and PAT.match(f.name)]
    top_prev = group_by_latest(prev_files)
    for f in prev_files:
        m = PAT.match(f.name)
        if not m:
            continue
        base, ver = m.group(1).lower(), int(m.group(2))
        if ver < top_prev[base]:
            logging.info(f"DELETE {f.name}  (older than latest in Previous Deals)")
            if not args.dry_run:
                f.unlink()

    logging.info("✅ Move_Old v3 complete.")


# ----------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Move old deal versions to Previous Deals folder")
    parser.add_argument('--keep', type=int, default=1, help='Number of newest versions to keep in Current Deals (default=1)')
    parser.add_argument('--dry-run', action='store_true', help='Preview actions without moving/deleting files')
    args = parser.parse_args()

    if args.keep < 1:
        parser.error('--keep must be >= 1')

    move_old(args)
