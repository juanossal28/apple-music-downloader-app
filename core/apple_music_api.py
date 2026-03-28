import re
from functools import lru_cache

import requests

from core.paths import get_amd_config_file


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.124 Safari/537.36"
)

TOKEN_ASSET_PATTERN = re.compile(r"/assets/index~[^/]+\.js")
TOKEN_PATTERN = re.compile(r'eyJh[^"]*')
CONFIG_LINE_PATTERN = re.compile(r"^\s*([^:#]+?)\s*:\s*(.*?)\s*$")


def fetch_metadata(link):
    metadata = fetch_amp_metadata(link)
    if metadata:
        return metadata

    return fetch_itunes_metadata(link)


def fetch_amp_metadata(link):
    storefront = extract_storefront(link)
    track_id, album_id = extract_ids(link)

    if not storefront:
        storefront = "us"

    token = get_amp_token()
    if not token:
        return None

    language = get_config_value("language", "")

    try:
        if track_id:
            response = requests.get(
                f"https://amp-api.music.apple.com/v1/catalog/{storefront}/songs/{track_id}",
                headers=_build_amp_headers(token),
                params={
                    "include": "albums,artists",
                    "extend": "extendedAssetUrls",
                    "l": language,
                },
                timeout=10,
            )
            response.raise_for_status()
            return _parse_amp_song_metadata(response.json(), album_id)

        if album_id:
            response = requests.get(
                f"https://amp-api.music.apple.com/v1/catalog/{storefront}/albums/{album_id}",
                headers=_build_amp_headers(token),
                params={
                    "omit[resource]": "autos",
                    "include": "tracks,artists,record-labels",
                    "include[songs]": "artists",
                    "extend": "editorialVideo,extendedAssetUrls",
                    "l": language,
                },
                timeout=10,
            )
            response.raise_for_status()
            return _parse_amp_album_metadata(response.json())
    except Exception:
        return None

    return None


def fetch_itunes_metadata(link):
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
            "artist_id": result.get("artistId"),
            "track": result.get("trackName"),
            "album": result.get("collectionName"),
            "album_id": result.get("collectionId") or album_id,
            "release_date": result.get("releaseDate"),
            "copyright": result.get("copyright"),
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

    if not track_id:
        song_match = re.search(r"/song/.+?/(\d+)", link)
        if song_match:
            track_id = song_match.group(1)

    album_match = re.search(r"/album/.+?/(\d+)", link)
    if album_match:
        album_id = album_match.group(1)

    return track_id, album_id


def extract_storefront(link):
    storefront_match = re.search(
        r"https://(?:beta\.music|music|classical\.music)\.apple\.com/([a-zA-Z]{2})/",
        link,
    )
    if storefront_match:
        return storefront_match.group(1).lower()

    return None


@lru_cache(maxsize=1)
def get_amp_token():
    config_token = get_config_value("authorization-token", "")
    if config_token and config_token != "your-authorization-token":
        return config_token.replace("Bearer ", "").strip()

    try:
        response = requests.get(
            "https://music.apple.com",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        asset_match = TOKEN_ASSET_PATTERN.search(response.text)
        if not asset_match:
            return None

        asset_response = requests.get(
            f"https://music.apple.com{asset_match.group(0)}",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        asset_response.raise_for_status()
        token_match = TOKEN_PATTERN.search(asset_response.text)
        if not token_match:
            return None

        return token_match.group(0)
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_config_value(key, default=""):
    config_file = get_amd_config_file()
    if not config_file.exists():
        return default

    try:
        for raw_line in config_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            match = CONFIG_LINE_PATTERN.match(line)
            if not match:
                continue

            current_key = match.group(1).strip()
            raw_value = _strip_inline_comment(match.group(2)).strip()
            if current_key != key:
                continue

            if raw_value and raw_value[0] in {'"', "'"} and raw_value[-1] == raw_value[0]:
                raw_value = raw_value[1:-1]

            return raw_value
    except Exception:
        return default

    return default


def _build_amp_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "Origin": "https://music.apple.com",
    }


def _parse_amp_song_metadata(data, fallback_album_id):
    items = (data or {}).get("data") or []
    if not items:
        return None

    song = items[0]
    attributes = song.get("attributes") or {}
    relationships = song.get("relationships") or {}
    album_items = ((relationships.get("albums") or {}).get("data")) or []
    artist_items = ((relationships.get("artists") or {}).get("data")) or []

    album_item = album_items[0] if album_items else {}
    album_attributes = album_item.get("attributes") or {}
    artist_item = artist_items[0] if artist_items else {}
    artist_attributes = artist_item.get("attributes") or {}

    return {
        "artist": (
            album_attributes.get("artistName")
            or artist_attributes.get("name")
            or attributes.get("artistName")
        ),
        "artist_id": artist_item.get("id"),
        "track": attributes.get("name"),
        "album": album_attributes.get("name") or attributes.get("albumName"),
        "album_id": album_item.get("id") or fallback_album_id,
        "release_date": album_attributes.get("releaseDate") or attributes.get("releaseDate"),
        "copyright": album_attributes.get("copyright"),
        "record_label": album_attributes.get("recordLabel"),
        "upc": album_attributes.get("upc"),
        "track_number": attributes.get("trackNumber"),
        "track_count": album_attributes.get("trackCount"),
    }


def _parse_amp_album_metadata(data):
    items = (data or {}).get("data") or []
    if not items:
        return None

    album = items[0]
    attributes = album.get("attributes") or {}
    relationships = album.get("relationships") or {}
    artist_items = ((relationships.get("artists") or {}).get("data")) or []
    artist_item = artist_items[0] if artist_items else {}
    artist_attributes = artist_item.get("attributes") or {}

    return {
        "artist": artist_attributes.get("name") or attributes.get("artistName"),
        "artist_id": artist_item.get("id"),
        "track": None,
        "album": attributes.get("name"),
        "album_id": album.get("id"),
        "release_date": attributes.get("releaseDate"),
        "copyright": attributes.get("copyright"),
        "record_label": attributes.get("recordLabel"),
        "upc": attributes.get("upc"),
        "track_number": None,
        "track_count": attributes.get("trackCount"),
    }


def _strip_inline_comment(value):
    in_single_quote = False
    in_double_quote = False
    result = []

    for char in value:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "#" and not in_single_quote and not in_double_quote:
            break

        result.append(char)

    return "".join(result)
