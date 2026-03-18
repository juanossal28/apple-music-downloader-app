import re

import requests


def fetch_metadata(link):
    track_id, album_id = extract_ids(link)

    if track_id:
        url = f"https://itunes.apple.com/lookup?id={track_id}"
    elif album_id:
        url = f"https://itunes.apple.com/lookup?id={album_id}&entity=song"
    else:
        return None

    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        results = data.get("results") or []

        if not results:
            return None

        result = results[0]
        return {
            "artist": result.get("artistName"),
            "track": result.get("trackName"),
            "album": result.get("collectionName"),
            "track_number": result.get("trackNumber"),
            "track_count": result.get("trackCount"),
        }
    except Exception:
        return None


def extract_ids(link):
    track_id = None
    album_id = None

    track_match = re.search(r"[?&]i=(\d+)", link)
    if track_match:
        track_id = track_match.group(1)

    song_match = re.search(r"/song(?:/.+)?/(?:id)?(\d+)", link)
    if not track_id and song_match:
        track_id = song_match.group(1)

    album_match = re.search(r"/album/.+?/(\d+)", link)
    if album_match:
        album_id = album_match.group(1)

    return track_id, album_id
