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
