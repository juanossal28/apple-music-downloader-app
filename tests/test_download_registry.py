import json
from pathlib import Path

from core.download_registry import (
    canonicalize_link,
    is_link_already_downloaded,
    register_downloaded_link,
    should_skip_download,
)


def test_registers_link_with_matching_media_file(tmp_path: Path):
    destination_root = tmp_path / 'downloads'
    registry_path = tmp_path / 'registry.json'
    song_path = destination_root / 'Artist' / 'Album' / '01 Intro.m4a'
    song_path.parent.mkdir(parents=True)
    song_path.write_text('data', encoding='utf-8')

    metadata = {
        'artist': 'Artist',
        'album': 'Album',
        'track': 'Intro',
        'track_number': 1,
    }

    assert register_downloaded_link(
        'https://music.apple.com/us/song/example/123',
        metadata,
        destination_root,
        registry_path,
    )
    saved_data = json.loads(registry_path.read_text(encoding='utf-8'))
    key = canonicalize_link('https://music.apple.com/us/song/example/123')

    assert saved_data[key]['files'] == ['Artist/Album/01 Intro.m4a']


def test_registry_only_skips_when_registered_files_still_exist(tmp_path: Path):
    destination_root = tmp_path / 'downloads'
    registry_path = tmp_path / 'registry.json'
    song_path = destination_root / 'Artist' / 'Album' / '01 Intro.m4a'
    song_path.parent.mkdir(parents=True)
    song_path.write_text('data', encoding='utf-8')

    metadata = {
        'artist': 'Artist',
        'album': 'Album',
        'track': 'Intro',
        'track_number': 1,
    }
    link = 'https://music.apple.com/us/song/example/123'

    register_downloaded_link(link, metadata, destination_root, registry_path)

    assert is_link_already_downloaded(link, destination_root, registry_path)

    song_path.unlink()

    assert not is_link_already_downloaded(link, destination_root, registry_path)


def test_should_skip_download_backfills_registry_from_existing_files(tmp_path: Path):
    destination_root = tmp_path / 'downloads'
    registry_path = tmp_path / 'registry.json'
    song_path = destination_root / 'AC_DC' / '2024 Album_ Live [ALAC]' / '01 Thunder.m4a'
    song_path.parent.mkdir(parents=True)
    song_path.write_text('data', encoding='utf-8')

    metadata = {
        'artist': 'AC/DC',
        'album': 'Album: Live',
        'track': 'Thunder',
        'track_number': 1,
    }
    link = 'https://music.apple.com/us/song/example/123?foo=bar'

    assert should_skip_download(link, metadata, destination_root, registry_path)
    assert is_link_already_downloaded(link, destination_root, registry_path)
