import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.download_detection import find_matching_media_files, is_already_downloaded


def canonicalize_link(link):
    raw_link = (link or '').strip()
    if not raw_link:
        return ''

    split_result = urlsplit(raw_link)
    normalized_query = urlencode(sorted(parse_qsl(split_result.query, keep_blank_values=True)))

    return urlunsplit((
        split_result.scheme.lower(),
        split_result.netloc.lower(),
        split_result.path,
        normalized_query,
        '',
    ))


def load_registry(registry_path):
    path = Path(registry_path)
    if not path.exists():
        return {}

    try:
        raw_data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}

    if not isinstance(raw_data, dict):
        return {}

    normalized_registry = {}
    for key, value in raw_data.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue

        files = value.get('files')
        if not isinstance(files, list):
            continue

        normalized_files = [file for file in files if isinstance(file, str) and file]
        if not normalized_files:
            continue

        normalized_registry[key] = {
            'original_link': value.get('original_link') or key,
            'files': sorted(set(normalized_files)),
        }

    return normalized_registry


def save_registry(registry_path, registry):
    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry, indent=2, sort_keys=True),
        encoding='utf-8',
    )


def is_link_already_downloaded(link, destination_root, registry_path):
    registry = load_registry(registry_path)
    entry = registry.get(canonicalize_link(link))
    if not entry:
        return False

    destination_root = Path(destination_root)
    registered_files = [destination_root / relative_path for relative_path in entry['files']]
    return bool(registered_files) and all(file_path.exists() for file_path in registered_files)


def register_downloaded_link(link, metadata, destination_root, registry_path):
    if not metadata or not destination_root:
        return False

    destination_root = Path(destination_root)
    matched_files = find_matching_media_files(metadata, destination_root)
    if not matched_files:
        return False

    relative_files = sorted({
        str(file_path.relative_to(destination_root))
        for file_path in matched_files
        if file_path.exists()
    })
    if not relative_files:
        return False

    registry = load_registry(registry_path)
    registry[canonicalize_link(link)] = {
        'original_link': link,
        'files': relative_files,
    }
    save_registry(registry_path, registry)
    return True


def should_skip_download(link, metadata, destination_root, registry_path):
    if is_link_already_downloaded(link, destination_root, registry_path):
        return True

    if is_already_downloaded(metadata, destination_root):
        register_downloaded_link(link, metadata, destination_root, registry_path)
        return True

    return False
