from pathlib import Path
import shutil
import os


def clean_go_build_subfolders():
    """Elimina subcarpetas dentro de %USERPROFILE%\\AppData\\Local\\go-build."""
    go_build_dir = Path(os.path.expandvars(r"%USERPROFILE%\AppData\Local\go-build"))

    if not go_build_dir.exists() or not go_build_dir.is_dir():
        return

    for child in go_build_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
