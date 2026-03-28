import json
import re
import unicodedata
from pathlib import Path

from core.apple_music_api import extract_ids


FORBIDDEN_PATH_CHARS = re.compile(r'[/\\<>:"|?*]')
PLACEHOLDER_PATTERN = re.compile(r"\{[^{}]+\}")

CONFUSABLE_CHAR_MAP = {
    "∃": "E",
    "Ɛ": "E",
    "€": "E",
    "Æ": "AE",
    "æ": "AE",
    "Œ": "OE",
    "œ": "OE",
    "Ø": "O",
    "ø": "O",
    "Ð": "D",
    "ð": "D",
    "Þ": "TH",
    "þ": "TH",
    "Ł": "L",
    "ł": "L",
    "ß": "SS",
}

DEFAULT_DOWNLOADER_CONFIG = {
    "artist-folder-format": "{UrlArtistName}",
    "album-folder-format": "{AlbumName}",
    "limit-max": 200,
}


def load_download_registry(registry_file: Path) -> dict:
    if not registry_file.exists():
        return {}

    try:
        data = json.loads(registry_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if isinstance(data, dict) and isinstance(data.get("downloads"), dict):
        return data["downloads"]

    return {}


def save_download_registry(registry_file: Path, downloads: dict) -> None:
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "downloads": downloads,
    }
    registry_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def read_downloader_config(config_file: Path) -> dict:
    config = DEFAULT_DOWNLOADER_CONFIG.copy()

    if not config_file.exists():
        return config

    for raw_line in config_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = _strip_inline_comment(raw_value).strip()

        if key not in config or not raw_value:
            continue

        if raw_value[0] in {'"', "'"} and raw_value[-1] == raw_value[0]:
            raw_value = raw_value[1:-1]

        if key == "limit-max":
            try:
                config[key] = int(raw_value)
            except ValueError:
                continue
        else:
            config[key] = raw_value

    return config


def build_download_key(link: str) -> str:
    normalized_link = (link or "").strip()
    track_id, album_id = extract_ids(normalized_link)

    if track_id:
        return f"track:{track_id}"

    if album_id:
        return f"album:{album_id}"

    return f"link:{normalized_link}"


def build_relative_download_path(metadata: dict | None, config: dict | None) -> Path | None:
    if not metadata:
        return None

    artist = _limit_value(metadata.get("artist"), config)
    album = _limit_value(metadata.get("album"), config)

    if not album:
        return None

    replacements = {
        "{UrlArtistName}": artist,
        "{ArtistName}": artist,
        "{ArtistId}": _limit_value(metadata.get("artist_id"), config),
        "{ReleaseDate}": _limit_value(metadata.get("release_date"), config),
        "{ReleaseYear}": _limit_value((metadata.get("release_date") or "")[:4], config),
        "{AlbumName}": album,
        "{AlbumId}": _limit_value(metadata.get("album_id"), config),
        "{UPC}": _limit_value(metadata.get("upc"), config),
        "{Copyright}": _limit_value(metadata.get("copyright"), config),
        "{Quality}": _limit_value(metadata.get("quality"), config),
        "{Codec}": _limit_value(metadata.get("codec"), config),
        "{Tag}": _limit_value(metadata.get("tag"), config),
        "{RecordLabel}": _limit_value(metadata.get("record_label"), config),
    }

    effective_config = config or DEFAULT_DOWNLOADER_CONFIG
    artist_folder = _render_folder_name(
        effective_config.get("artist-folder-format", ""),
        replacements,
    )
    album_folder = _render_folder_name(
        effective_config.get("album-folder-format", "{AlbumName}"),
        replacements,
    )

    if not album_folder:
        return None

    if artist_folder:
        return Path(artist_folder) / album_folder

    return Path(album_folder)


def sanitize_path_component(value: str | None) -> str:
    cleaned_value = (value or "").strip()
    if not cleaned_value:
        return ""

    if cleaned_value.endswith("."):
        cleaned_value = cleaned_value.replace(".", "")

    cleaned_value = cleaned_value.strip()
    cleaned_value = FORBIDDEN_PATH_CHARS.sub("_", cleaned_value)
    return cleaned_value.strip()


def normalize_for_match(value: str | None) -> str:
    if not value:
        return ""

    translated = "".join(CONFUSABLE_CHAR_MAP.get(char, char) for char in value)
    normalized = unicodedata.normalize("NFKC", translated).casefold()

    kept_chars = []
    for char in normalized:
        category = unicodedata.category(char)
        if category.startswith(("L", "N")):
            kept_chars.append(char)

    return "".join(kept_chars)


def _render_folder_name(template: str, replacements: dict[str, str]) -> str:
    rendered = template or ""

    for key, value in replacements.items():
        rendered = rendered.replace(key, value)

    rendered = PLACEHOLDER_PATTERN.sub("", rendered)
    return sanitize_path_component(rendered)


def _strip_inline_comment(raw_value: str) -> str:
    in_single_quote = False
    in_double_quote = False
    stripped_chars = []

    for char in raw_value:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "#" and not in_single_quote and not in_double_quote:
            break

        stripped_chars.append(char)

    return "".join(stripped_chars).strip()


def _limit_value(value, config: dict | None) -> str:
    text = "" if value is None else str(value)
    limit = (config or DEFAULT_DOWNLOADER_CONFIG).get("limit-max", 200)
    return text[:limit]
