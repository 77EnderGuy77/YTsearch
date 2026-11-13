import time
from googleapiclient.errors import HttpError
import logging
import yaml
from pathlib import Path

CONFIG_FILE = Path('config.yaml')
logger = logging.getLogger(__name__)

def get_or_create_playlist(youtube,
                           title: str,
                           description: str = '',
                           privacy: str = 'private') -> str:
    """
    Ensure a playlist with the given title exists. If cfg['playlist_id'] is already
    present, reuse it. Otherwise list/create with retry‐on‐quota.
    Returns the playlist ID.
    """
    # 0) Check config first
    cfg = yaml.safe_load(CONFIG_FILE.read_text(encoding='utf-8'))
    existing = cfg.get('playlist_id')
    if existing:
        logger.info("Found existing playlist_id %s in config → skipping lookup", existing)
        return existing

    # 1) Try to list existing playlists (with quota‐retry)
    while True:
        try:
            resp = youtube.playlists().list(
                part='snippet,status',
                mine=True,
                maxResults=50
            ).execute()
            break
        except HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                logger.warning("quotaExceeded on list ⇒ retrying in 1 hour…")
                time.sleep(3600)
                continue
            logger.error("Failed to list playlists: %s", e)
            raise

    # 2) Reuse if title matches
    for pl in resp.get('items', []):
        if pl['snippet']['title'] == title:
            pid = pl['id']
            logger.info("Reusing existing playlist '%s' (ID: %s)", title, pid)
            # Save back to config for next run
            cfg['playlist_id'] = pid
            CONFIG_FILE.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding='utf-8')
            return pid

    # 3) Create new playlist (with quota‐retry)
    body = {
        'snippet': {'title': title, 'description': description},
        'status':  {'privacyStatus': privacy}
    }
    while True:
        try:
            created = youtube.playlists().insert(
                part='snippet,status',
                body=body
            ).execute()
            pid = created['id']
            logger.info("Created playlist '%s' (ID: %s)", title, pid)
            # Save to config
            cfg['playlist_id'] = pid
            CONFIG_FILE.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding='utf-8')
            return pid
        except HttpError as e:
            if e.resp.status == 403 and 'quotaExceeded' in str(e):
                logger.warning("quotaExceeded on create ⇒ retrying in 1 hour…")
                time.sleep(3600)
                continue
            logger.error("Failed to create playlist '%s': %s", title, e)
            raise



def add_videos_to_playlist(youtube, playlist_id: str, video_ids: list):
    """
    Adds each video ID to the given playlist one at a time.
    If we hit quotaExceeded on an insert, wait 1 hour then retry that video.
    """
    for vid in video_ids:
        body = {
            'snippet': {
                'playlistId': playlist_id,
                'resourceId': {'kind': 'youtube#video', 'videoId': vid}
            }
        }
        while True:
            try:
                resp = youtube.playlistItems().insert(part='snippet', body=body).execute()
                item_id = resp['id']
                logger.info("✅ Added video %s as playlistItem %s", vid, item_id)
                break
            except HttpError as e:
                err = str(e)
                if e.resp.status == 403 and 'quotaExceeded' in err:
                    logger.warning("quotaExceeded on insert %s⇒ retrying in 1 hour…", vid)
                    time.sleep(3600)
                    continue
                status = getattr(e.resp, 'status', None)
                logger.error("❌ Failed to add %s (HTTP %s): %s", vid, status, e)
                break
