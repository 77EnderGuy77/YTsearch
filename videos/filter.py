import csv
from pathlib import Path
import loaders
import logging

logger = logging.getLogger(__name__)

def filter_videos(config_path: Path, old_csv: Path, new_csv: Path):
    """
    Reads all video records from old_csv, applies include/exclude and CID filters
    based on config.yaml, and writes all remaining fields (including 'CID')
    into new_csv. Only new (not already written) rows are added.
    """
    # Load configuration
    cfg = loaders.load_file(config_path)
    includes = [w.lower() for w in cfg.get('include', [])]
    excludes = [w.lower() for w in cfg.get('exclude', [])]
    cid_list = cfg.get('f4m_save', [])  # list of CIDs to always include

    logger.info(f"Loaded config: include={includes}, exclude={excludes}, always_save_cids={cid_list}")

    # Read all existing records from old_csv
    with old_csv.open(newline='', encoding='utf-8') as f_in:
        reader = csv.DictReader(f_in)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    logger.info(f"Read {len(rows)} rows from {old_csv}")

    # Load already written IDs from new_csv (if exists)
    existing_ids = set()
    if new_csv.exists():
        with new_csv.open(newline='', encoding='utf-8') as f_out:
            reader = csv.DictReader(f_out)
            for row in reader:
                # Use 'Video Id' as unique key; change if needed
                existing_ids.add(row.get('Video Id'))

    logger.info(f"Found {len(existing_ids)} existing IDs in {new_csv}")

    # Prepare output file
    is_new = not new_csv.exists()
    passed = 0
    with new_csv.open('a', newline='', encoding='utf-8') as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
            logger.info(f"Wrote header to new file {new_csv}")

        for row in rows:
            video_id = row.get('Video Id')
            if video_id in existing_ids:
                logger.debug(f"Duplicate: skipped {video_id}")
                continue

            title = row.get('Video Title', '').lower()
            desc  = row.get('Description', '').lower()
            tags  = row.get('Tags', '').lower()
            cid   = row.get('CID', '')

            text = ' '.join([title, desc, tags])

            # Always include if CID in f4m_save
            if cid in cid_list:
                writer.writerow(row)
                passed += 1
                logger.debug(f"CID match: wrote row for CID={cid}")
                continue

            # Include/exclude filtering
            if includes and not any(word in text for word in includes):
                logger.debug(f"Exclude by include-list: skipped {video_id}")
                continue
            if excludes and any(word in text for word in excludes):
                logger.debug(f"Exclude by exclude-list: skipped {video_id}")
                continue

            # Write full row if passes
            writer.writerow(row)
            passed += 1
            logger.debug(f"Wrote row for Video Id={video_id}")

    logger.info(f"Filtering complete: {passed} new rows written to {new_csv}")

if __name__ == "__main__":
    cfgPath = Path("config.yaml")
    oldCSV = Path('videos.csv')
    newCSV = Path('filter.csv')
    filter_videos(cfgPath, oldCSV, newCSV)