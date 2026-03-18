from pathlib import Path

from core.download_detection import is_already_downloaded


def test_detects_exact_artist_and_album_folder(tmp_path: Path):
    album_dir = tmp_path / 'Artist' / 'Album'
    album_dir.mkdir(parents=True)
    (album_dir / '01 - Song.m4a').write_text('data', encoding='utf-8')

    assert is_already_downloaded({'artist': 'Artist', 'album': 'Album'}, tmp_path)


def test_detects_sanitized_and_formatted_folder_names(tmp_path: Path):
    album_dir = tmp_path / 'AC_DC' / '2024 Album_ Live [ALAC]'
    album_dir.mkdir(parents=True)
    (album_dir / '01 - Intro.m4a').write_text('data', encoding='utf-8')

    metadata = {'artist': 'AC/DC', 'album': 'Album: Live'}
    assert is_already_downloaded(metadata, tmp_path)


def test_ignores_matching_folder_without_media_files(tmp_path: Path):
    album_dir = tmp_path / 'Artist' / 'Album'
    album_dir.mkdir(parents=True)
    (album_dir / 'cover.jpg').write_text('data', encoding='utf-8')

    assert not is_already_downloaded({'artist': 'Artist', 'album': 'Album'}, tmp_path)
