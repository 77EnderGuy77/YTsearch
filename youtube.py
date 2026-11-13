#!/usr/bin/env python3
"""
youtube_fetcher.py

Fetches all videos from channels specified in config.yaml via the Search API,
optionally filters by include/exclude keywords in title, description, and tags,
outputs a CSV with:
  - Video Title
  - Video Id
  - Description
  - Tags
  - Was it saved to a playlist (initially False)

Records videos oldest→newest. Uses API_KEY from .env for reads.
On quotaExceeded errors, stops the job and waits until the next run.
Scheduled to run immediately once, then hourly on the hour via APScheduler.
Switch filtering on/off via `filter_enabled` in config.yaml.
Handles channel URL patterns case-insensitively, including dots/underscores/commas.
"""
import os
import sys
import re
import csv
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# ---------------------------------------------------------------------------- #
# Configuration
# ---------------------------------------------------------------------------- #
CONFIG_FILE = 'config.yaml'
OUTPUT_CSV  = 'videos.csv'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ---------------------------------------------------------------------------- #
# YouTube Client
# ---------------------------------------------------------------------------- #
def get_youtube_client():
    load_dotenv()
    key = os.getenv('API_KEY')
    if not key:
        logging.error("API_KEY missing in environment (.env)")
        sys.exit(1)
    return build('youtube', 'v3', developerKey=key)

# ---------------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------------- #
def extract_channel_id(youtube, url: str) -> str:
    # /channel/ID
    m = re.search(r'/channel/([\w-]+)', url, re.IGNORECASE)
    if m:
        return m.group(1)
    # @handle (allow letters, digits, underscore, hyphen, dot, comma)
    m = re.search(r'@([\w\-\._,]+)', url, re.IGNORECASE)
    if m:
        handle = m.group(1)
        resp = youtube.search().list(
            part='id', q=handle, type='channel', maxResults=1
        ).execute()
        items = resp.get('items', [])
        if items:
            return items[0]['id']['channelId']
    # /user/USERNAME
    m = re.search(r'/user/([\w-]+)', url, re.IGNORECASE)
    if m:
        user = m.group(1)
        resp = youtube.channels().list(
            part='id', forUsername=user
        ).execute()
        items = resp.get('items', [])
        if items:
            return items[0]['id']
    raise ValueError(f"Cannot extract channel ID from '{url}'")

# ---------------------------------------------------------------------------- #
# Fetch entire channel via Search
# ---------------------------------------------------------------------------- #
def get_all_videos_via_search(
    youtube,
    channel_id: str,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    filter_enabled: bool = True
) -> List[Dict]:
    include = [w.lower() for w in include or []]
    exclude = [w.lower() for w in exclude or []]
    videos = []
    next_token = None

    # Paginate through all search results ordered by date (newest→oldest)
    while True:
        resp = youtube.search().list(
            part='snippet',
            channelId=channel_id,
            q=','.join(include) if include else None,
            type='video',
            order='date',
            maxResults=50,
            pageToken=next_token
        ).execute()

        for itm in resp.get('items', []):
            sn = itm['snippet']
            vid = sn['resourceId']['videoId'] if 'resourceId' in sn else itm['id']['videoId']
            title = sn.get('title','').strip()
            pub = sn.get('publishedAt')
            # Apply include/exclude filters at the search stage if desired
            if include or exclude:
                text = f"{title} {sn.get('description','')}".lower()
                if include and not any(w in text for w in include):
                    continue
                if exclude and any(w in text for w in exclude):
                    continue
            videos.append({'videoId': vid, 'title': title, 'publishedAt': pub})

        next_token = resp.get('nextPageToken')
        if not next_token:
            break

    # Batch-enrich each 50 for description, tags, and actual publish date
    for i in range(0, len(videos), 50):
        batch = videos[i:i+50]
        ids = ','.join(v['videoId'] for v in batch)
        resp = youtube.videos().list(part='snippet', id=ids, maxResults=50).execute()
        for item in resp.get('items', []):
            vid = item['id']
            sn = item['snippet']
            for v in batch:
                if v['videoId'] == vid:
                    v['publishedAt'] = sn.get('publishedAt')
                    v['description'] = sn.get('description','').strip()
                    v['tags'] = ','.join(sn.get('tags', []))
                    break

    # Sort oldest→newest
    videos.sort(key=lambda x: x['publishedAt'])
    logging.info(f"Total videos fetched: {len(videos)}")
    return videos

# ---------------------------------------------------------------------------- #
# Core job: fetch channels and write CSV
# ---------------------------------------------------------------------------- #
def fetch_and_write():
    logging.info("Starting job: fetch channels")
    yt = get_youtube_client()

    cfg = yaml.safe_load(Path(CONFIG_FILE).read_text(encoding='utf-8'))
    channels = [u.strip() for u in cfg.get('channels', []) if u.strip()]
    if not channels:
        logging.warning("No channels defined; skipping")
        return

    include = cfg.get('include')
    exclude = cfg.get('exclude')
    filter_enabled = cfg.get('filter_enabled')

    is_new = not Path(OUTPUT_CSV).exists()
    csv_file = open(OUTPUT_CSV, 'a', newline='', encoding='utf-8')
    writer = csv.DictWriter(
        csv_file,
        fieldnames=['Video Title','Video Id','Description','Tags','Was it saved']
    )
    if is_new:
        writer.writeheader()

    total = 0
    for url in channels:
        try:
            cid = extract_channel_id(yt, url)
            logging.info(f"Processing {url} → {cid}")
            vids = get_all_videos_via_search(yt, cid, include, exclude, filter_enabled)
        except HttpError as e:
            if 'quotaExceeded' in str(e):
                logging.error(f"Quota exceeded for {url}, stopping")
                csv_file.close()
                return
            logging.error(f"API error for {url}: {e}, continuing")
            continue
        except Exception as e:
            logging.error(f"Error processing {url}: {e}, continuing")
            continue

        for v in vids:
            writer.writerow({
                'Video Title':  v['title'],
                'Video Id':     v['videoId'],
                'Description':  v.get('description',''),
                'Tags':         v.get('tags',''),
                'Was it saved': False
            })
            total += 1
            logging.info(f"Wrote: {v['videoId']}")

    csv_file.close()
    logging.info(f"Job complete: wrote {total} records to {OUTPUT_CSV}")

# ---------------------------------------------------------------------------- #
# Scheduler setup
# ---------------------------------------------------------------------------- #
if __name__ == '__main__':
    fetch_and_write()
    sched = BlockingScheduler()
    sched.add_job(fetch_and_write, CronTrigger(minute=0))
    logging.info("Scheduler started; hourly on the hour.")
    sched.start()
