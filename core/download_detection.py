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


def _iter_media_files(path: Path):
    for child in path.rglob('*'):
        if child.is_file() and child.suffix.lower() in MEDIA_EXTENSIONS:
            yield child


def _file_matches_track(file_path: Path, track_name, track_number):
    stem = normalize_for_matching(file_path.stem)
    normalized_track_name = normalize_for_matching(track_name)
    normalized_track_number = str(track_number or '').zfill(2)

    if normalized_track_name and normalized_track_name in stem:
        return True

    if normalized_track_number and file_path.stem.startswith(normalized_track_number):
        return True

    return False


def find_matching_album_dirs(metadata, destination_root):
    if not metadata or not destination_root:
        return []

    artist = metadata.get('artist')
    album = metadata.get('album')
    if not artist or not album:
        return []

    destination_root = Path(destination_root)
    if not destination_root.exists() or not destination_root.is_dir():
        return []

    matches = []
    seen = set()

    direct_album_path = (
        destination_root /
        sanitize_component(artist) /
        sanitize_component(album)
    )
    if direct_album_path.is_dir():
        matches.append(direct_album_path)
        seen.add(direct_album_path.resolve())

    for artist_dir in destination_root.iterdir():
        if not artist_dir.is_dir() or not _dir_name_matches(artist_dir.name, artist):
            continue

        for album_dir in artist_dir.iterdir():
            if not album_dir.is_dir() or not _dir_name_matches(album_dir.name, album):
                continue

            resolved_album_dir = album_dir.resolve()
            if resolved_album_dir in seen:
                continue

            matches.append(album_dir)
            seen.add(resolved_album_dir)

    return matches


def find_matching_media_files(metadata, destination_root):
    album_dirs = find_matching_album_dirs(metadata, destination_root)
    if not album_dirs:
        return []

    media_files = []
    for album_dir in album_dirs:
        media_files.extend(_iter_media_files(album_dir))

    if not media_files:
        return []

    track_name = metadata.get('track')
    track_number = metadata.get('track_number')

    if track_name or track_number:
        matched_tracks = [
            file_path
            for file_path in media_files
            if _file_matches_track(file_path, track_name, track_number)
        ]
        if matched_tracks:
            return sorted(matched_tracks)

    return sorted(media_files)


def is_already_downloaded(metadata, destination_root):
    return bool(find_matching_media_files(metadata, destination_root))
