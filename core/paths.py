from pathlib import Path
import sys


def get_project_root() -> Path:
    """Return the runtime root folder both in source and bundled builds."""
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def get_amd_workdir() -> Path:
    """Return the bundled/local apple-music-downloader folder path."""
    return get_project_root() / "data" / "apple-music-downloader-main"


def get_amd_downloads_dir() -> Path:
    """Return the folder where AM-DL writes downloaded files by default."""
    return get_amd_workdir() / "AM-DL downloads"


def get_download_destination_file() -> Path:
    """Return the settings file that stores the user-selected destination path."""
    return get_project_root() / "data" / "download_destination.txt"


def get_download_registry_file() -> Path:
    """Return the persistent registry used to prevent duplicate downloads."""
    return get_project_root() / "data" / "download_registry.json"
