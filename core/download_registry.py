from __future__ import annotations

import json
from pathlib import Path


class DownloadRegistry:
    def __init__(self, registry_file: Path):
        self.registry_file = registry_file
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        self._entries = self._load()

    def _load(self):
        if not self.registry_file.exists():
            return {}

        try:
            data = json.loads(self.registry_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(data, dict):
            return {}

        return {
            str(key): value
            for key, value in data.items()
            if isinstance(value, dict)
        }

    def save(self):
        self.registry_file.write_text(
            json.dumps(self._entries, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get(self, key: str):
        return self._entries.get(key)

    def remove(self, key: str):
        if key not in self._entries:
            return

        self._entries.pop(key, None)
        self.save()

    def is_downloaded(self, key: str) -> bool:
        entry = self._entries.get(key)
        if not entry:
            return False

        target_folder = Path(entry.get("target_folder", ""))
        if not target_folder.exists() or not target_folder.is_dir():
            self.remove(key)
            return False

        if not any(path.is_file() for path in target_folder.rglob("*")):
            self.remove(key)
            return False

        return True

    def mark_downloaded(self, key: str, link: str, target_folder: Path, metadata=None):
        entry = {
            "link": link,
            "target_folder": str(target_folder),
        }
        if metadata:
            entry["metadata"] = metadata

        self._entries[key] = entry
        self.save()
