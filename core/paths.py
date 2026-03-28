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
    """Return the registry file that stores successfully downloaded links."""
    return get_project_root() / "data" / "download_registry.json"


def get_amd_config_file() -> Path:
    """Return the bundled/local downloader config file path."""
    return get_amd_workdir() / "config.yaml"


def get_emulator_launch_mode_file() -> Path:
    """Return the settings file that stores whether the emulator starts hidden."""
    return get_project_root() / "data" / "emulator_launch_mode.txt"
