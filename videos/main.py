# ---------------------------------------------------------------------------- #
# Imports
# ---------------------------------------------------------------------------- #
import csv
import logging
import os
import pickle
import re
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow

import filter
import get_vids
import loaders
import saves
from playlist_utils import add_videos_to_playlist, get_or_create_playlist

# ---------------------------------------------------------------------------- #
# Configuration
# ---------------------------------------------------------------------------- #
CONFIG_FILE   = Path('config.yaml')
NOFILTER_CSV  = Path('videos.csv')
FILTER_CSV    = Path('filter.csv')

# Set up module-level logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ---------------------------------------------------------------------------- #
# YouTube
# ---------------------------------------------------------------------------- #

def get_youtube_client():
    load_dotenv()
    key = os.getenv('API_KEY')
    if not key:
        logger.error("API_KEY missing in environment (.env)")
        sys.exit(1)
    return build('youtube', 'v3', developerKey=key)

def get_oauth_client():
    """
    Build an OAuth2-authenticated YouTube client (credentials stored in token.pickle).
    Automatically re-prompts if the saved token is invalid, using a local server.
    """


    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
    token_path = Path("token.pickle")
    creds = None

    # 1) Load existing creds if present
    if token_path.exists():
        creds = pickle.loads(token_path.read_bytes())

    # 2) Try refresh or force a new flow on failure
    try:
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise RefreshError("Triggering new OAuth flow")
    except RefreshError:
        # Remove bad token and start fresh
        if token_path.exists():
            token_path.unlink()
        flow = InstalledAppFlow.from_client_secrets_file(
            "client_secrets.json", SCOPES
        )
        # Launch a local server; your browser will open for consent
        creds = flow.run_console()

    # 3) Persist updated tokens
    token_path.write_bytes(pickle.dumps(creds))

    # 4) Return an OAuth-authorized client
    return build("youtube", "v3", credentials=creds)

# ---------------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------------- #

def get_channel_id(youtube, url: str) -> str:
    m = re.search(r'@([\w\-\._,]+)', url, re.IGNORECASE)
    if not m:
        logger.error("%s is not a valid channel handle", url)
        return None

    handle = '@' + m.group(1)
    try:
        resp = youtube.channels().list(
            part='id,snippet,statistics', forHandle=handle
        ).execute()
    except HttpError as e:
        logger.error("Error fetching channel for %s: %s", handle, e)
        return None

    items = resp.get('items', [])
    if not items:
        logger.warning("No channel found for handle %s", handle)
        return None

    info = items[0]
    title = info['snippet'].get('title', 'Unknown')
    count = info['statistics'].get('videoCount', 'N/A')
    logger.info("Channel '%s' has %s videos", title, count)
    return info.get('id')

# ---------------------------------------------------------------------------- #
# Main function
# ---------------------------------------------------------------------------- #

def main():
    cfg = loaders.load_config(CONFIG_FILE)
    # API-key client for read-only:
    yt_ro = get_youtube_client()

    yt_rw = get_oauth_client()

    channels = cfg.get('channels', [])
    if not channels:
        logger.warning("No channels configured; exiting.")
        return

    playlistID = get_or_create_playlist(yt_rw, cfg['playlist_title'])

    cids = cfg.get('channel_ids', []) or []

    # Resolve missing channel IDs
    if len(cids) < len(channels):
        updated_ids = []
        for url in channels:
            cid = get_channel_id(yt_ro, url)
            if cid:
                updated_ids.append(cid)
        cfg['channel_ids'] = updated_ids
        saves.save_ids(CONFIG_FILE, list(zip(channels, updated_ids)))
        cids = updated_ids

    # Fetch videos
    logger.info("Fetching videos for %d channels", len(cids))
    try:
        videos = get_vids.get_vids(yt_ro, cids)
    except HttpError as e:
        if getattr(e.resp, 'status', None) == 403 and 'quotaExceeded' in str(e):
            logger.error("Quota exceeded; aborting")
            return
        logger.error("Error fetching videos: %s", e)
        raise
    logger.info("Fetched %d videos", len(videos))

    # Write all videos
    is_new = not NOFILTER_CSV.exists()
    with NOFILTER_CSV.open('a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=['Video Title','Video Id','Description','Tags','Was it saved','CID']
        )
        if is_new:
            writer.writeheader()
        for v in videos:
            writer.writerow({
                'Video Title': v['title'],
                'Video Id':    v['videoId'],
                'Description': v.get('description',''),
                'Tags':        v.get('tags',''),
                'Was it saved': False,
                'CID':          v['CID']
            })
    logger.info("Wrote %d records to %s", len(videos), NOFILTER_CSV)

    # Filtering
    logger.info("Filtering videos")
    filter.filter_videos(CONFIG_FILE, NOFILTER_CSV, FILTER_CSV)
    
    with FILTER_CSV.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        video_ids = [row['Video Id'] for row in reader]
    
    logger.info("Starting the adding to a playlist")
    add_videos_to_playlist(yt_rw, playlistID, video_ids)

if __name__ == '__main__':
    main()
    scheduler = BlockingScheduler()
    scheduler.add_job(main, CronTrigger(minute=0))
    logger.info("Scheduler started; hourly.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down.")
        scheduler.shutdown()
