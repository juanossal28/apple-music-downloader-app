import json
from pathlib import Path

from core.paths import get_project_root


class DownloadRegistry:
    def __init__(self, registry_file=None):
        self.registry_file = registry_file or (
            get_project_root() / "data" / "download_history.json"
        )
        self._entries = self._load()

    def _load(self):
        if not self.registry_file.exists():
            return {}

        try:
            data = json.loads(self.registry_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        if not isinstance(data, dict):
            return {}

        normalized = {}
        for link, entry in data.items():
            if not isinstance(link, str) or not isinstance(entry, dict):
                continue

            folder = entry.get("folder")
            if not isinstance(folder, str) or not folder.strip():
                continue

            normalized[link] = {
                "folder": folder,
                "artist": entry.get("artist"),
                "album": entry.get("album"),
            }

        return normalized

    def save(self):
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            self._entries,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        self.registry_file.write_text(f"{content}\n", encoding="utf-8")

    def get_entry(self, link):
        return self._entries.get(link)

    def remove(self, link):
        if link in self._entries:
            self._entries.pop(link, None)
            self.save()

    def register(self, link, folder_path, metadata=None):
        entry = {
            "folder": str(folder_path),
            "artist": metadata.get("artist") if metadata else None,
            "album": metadata.get("album") if metadata else None,
        }
        self._entries[link] = entry
        self.save()

    def is_download_available(self, link):
        entry = self.get_entry(link)
        if not entry:
            return True

        folder = Path(entry["folder"])
        if not self._folder_has_files(folder):
            self.remove(link)
            return True

        return False

    def resolve_folder_path(self, destination_root, metadata):
        if not destination_root or not metadata:
            return None

        artist = metadata.get("artist")
        album = metadata.get("album")
        if not artist or not album:
            return None

        return Path(destination_root) / artist / album

    def register_if_folder_present(self, link, folder_path, metadata=None):
        folder = Path(folder_path)
        if not self._folder_has_files(folder):
            return False

        self.register(link, folder, metadata)
        return True

    def register_if_present(self, link, destination_root, metadata):
        folder_path = self.resolve_folder_path(destination_root, metadata)
        if folder_path is None:
            return False

        return self.register_if_folder_present(link, folder_path, metadata)

    @staticmethod
    def _folder_has_files(folder):
        if not folder.exists() or not folder.is_dir():
            return False

        return any(path.is_file() for path in folder.rglob("*"))
