import logging
import csv
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import Resource

logger = logging.getLogger(__name__)

def get_vids(
    youtube: Resource,
    cids: List[str],
    existing_csv_path: str = 'videos.csv'
) -> List[Dict[str, Any]]:
    """
    Fetch only new videos (not present in existing CSV) for each channel:
      - Uses youtube.search().list ordered by date (newest→oldest), 50 per page.
      - Stops paging once a known video ID is encountered to reduce API calls.
      - Enriches new videos via youtube.videos().list in batches of 50.
    """
    videos: List[Dict[str, Any]] = []

    # Load existing video IDs to skip duplicates
    existing_ids = set()
    try:
        with open(existing_csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                vid = row.get('Video Id') or row.get('videoId')
                if vid:
                    existing_ids.add(vid)
    except FileNotFoundError:
        logger.info("No existing CSV found at %s, fetching all videos", existing_csv_path)

    # Phase 1: collect only new IDs, stop on first known per channel
    for cid in cids:
        logger.info("Collecting new videos for channel %s", cid)
        next_token: Optional[str] = None
        while True:
            resp = youtube.search().list(
                part='id,snippet',
                channelId=cid,
                type='video',
                order='date',
                maxResults=50,
                pageToken=next_token
            ).execute()
            items = resp.get('items', [])

            # If any vid is known, stop further paging
            halt = False
            for itm in items:
                vid = itm['id']['videoId']
                if vid in existing_ids:
                    halt = True
                    break
                sn = itm['snippet']
                videos.append({
                    'CID':        cid,
                    'videoId':    vid,
                    'title':      sn.get('title','').strip(),
                    'publishedAt':sn.get('publishedAt'),
                })
                existing_ids.add(vid)

            if halt:
                break
            next_token = resp.get('nextPageToken')
            if not next_token:
                break

    logger.info("Total new raw videos: %d", len(videos))

    # Phase 2: enrich new videos in batches
    for i in range(0, len(videos), 50):
        batch = videos[i:i+50]
        ids = ','.join(v['videoId'] for v in batch)
        resp = youtube.videos().list(part='snippet', id=ids).execute()
        for item in resp.get('items', []):
            vid = item['id']
            sn = item['snippet']
            for v in batch:
                if v['videoId'] == vid:
                    v['description'] = sn.get('description','').strip()
                    v['tags']        = ','.join(sn.get('tags', []))
                    v['publishedAt'] = sn.get('publishedAt', v['publishedAt'])
                    break

    videos.sort(key=lambda x: x.get('publishedAt') or "")
    logger.info("Fetched and enriched %d new videos", len(videos))
    return videos
