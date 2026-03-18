from pathlib import Path
import re

FORBIDDEN_CHARS_RE = re.compile(r'[/\\<>:"|?*]')
NORMALIZE_RE = re.compile(r'[^a-z0-9]+')
MEDIA_EXTENSIONS = {
    '.m4a',
    '.mp4',
    '.flac',
    '.alac',
    '.aac',
    '.wav',
    '.mp3',
    '.ogg',
    '.opus',
}


def sanitize_component(value):
    value = (value or '').strip()
    if not value:
        return ''

    sanitized = FORBIDDEN_CHARS_RE.sub('_', value)
    if sanitized.endswith('.'):
        sanitized = sanitized.rstrip('.')

    return sanitized.strip()


def normalize_for_matching(value):
    sanitized = sanitize_component(value).lower()
    return NORMALIZE_RE.sub('', sanitized)


def _dir_name_matches(actual_name, expected_name):
    actual = normalize_for_matching(actual_name)
    expected = normalize_for_matching(expected_name)
    if not actual or not expected:
        return False

    return expected in actual or actual in expected


def _has_downloaded_media_files(path: Path):
    return any(
        child.is_file() and child.suffix.lower() in MEDIA_EXTENSIONS
        for child in path.rglob('*')
    )


def is_already_downloaded(metadata, destination_root):
    if not metadata or not destination_root:
        return False

    artist = metadata.get('artist')
    album = metadata.get('album')
    if not artist or not album:
        return False

    destination_root = Path(destination_root)
    if not destination_root.exists() or not destination_root.is_dir():
        return False

    direct_album_path = (
        destination_root /
        sanitize_component(artist) /
        sanitize_component(album)
    )
    if direct_album_path.is_dir() and _has_downloaded_media_files(direct_album_path):
        return True

    for artist_dir in destination_root.iterdir():
        if not artist_dir.is_dir() or not _dir_name_matches(artist_dir.name, artist):
            continue

        for album_dir in artist_dir.iterdir():
            if not album_dir.is_dir() or not _dir_name_matches(album_dir.name, album):
                continue
            if _has_downloaded_media_files(album_dir):
                return True

    return False
