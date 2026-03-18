import os
import signal
import subprocess
import threading
from pathlib import Path

from core.paths import get_amd_workdir


class DownloadTask:
    MAX_RETRIES = 3
    _CAPTURE_PREFIXES = ("Song->", "Album->", "Playlist->", "Station->")
    _NON_FOLDER_PREFIXES = (
        "Queue ",
        "Track ",
        "Audio:",
        "Video:",
        "Downloading",
        "Decrypting",
        "MV ",
        "Found ",
        "Animation ",
        "Animated ",
        "Connected ",
        "Invalid ",
        "Failed ",
        "Error",
        "Start trying again",
        "=======",
    )

    def __init__(self, link, log_callback, on_finished=None):
        self.link = link
        self.log_callback = log_callback
        self.on_finished = on_finished
        self.process = None
        self.relative_album_path = None
        self._artist_folder_name = None
        self._album_folder_name = None
        self._cancel_requested = False
        self._lock = threading.Lock()

    def start(self):
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()

    def run(self):
        retry_count = 0

        process = subprocess.Popen(
            ["go", "run", "main.go", "--song", self.link],
            cwd=str(get_amd_workdir()),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )

        with self._lock:
            self.process = process
            if self._cancel_requested:
                self._kill_process_tree(process)

        if process.stdout is None:
            process.wait()
            self._finish(process)
            return

        while True:
            if self._cancel_requested:
                self._kill_process_tree(process)
                break

            line = process.stdout.readline()
            if not line:
                break

            clean_line = line.strip()
            if not clean_line:
                continue

            if clean_line.startswith("Downloading"):
                try:
                    percent = clean_line.split("%")[0].split()[-1]
                    self.log_callback.emit(f"[PROGRESS] Downloading... {percent}%")
                except Exception:
                    pass
                continue

            if clean_line.startswith("Decrypting"):
                try:
                    percent = clean_line.split("%")[0].split()[-1]
                    self.log_callback.emit(f"[PROGRESS] Decrypting... {percent}%")
                except Exception:
                    pass
                continue

            self._capture_output_folder(clean_line)
            self.log_callback.emit(clean_line)

            if "press Enter to try again" in clean_line:
                if retry_count < self.MAX_RETRIES:
                    self.log_callback.emit(
                        f"[AUTO RETRY] Attempt {retry_count + 1}/{self.MAX_RETRIES}"
                    )

                    try:
                        if process.stdin is not None:
                            process.stdin.write("\n")
                            process.stdin.flush()
                            retry_count += 1
                    except Exception:
                        pass
                else:
                    self.log_callback.emit(
                        "[AUTO RETRY] Max retries reached. Skipping..."
                    )

        process.wait()
        self._finish(process)

    def _capture_output_folder(self, clean_line):
        if self.relative_album_path is not None:
            return

        artist_name = self._extract_prefixed_name(clean_line)
        if artist_name:
            self._artist_folder_name = artist_name
            self._update_relative_album_path()
            return

        if not self._looks_like_folder_name(clean_line):
            return

        if self._artist_folder_name is None:
            self._artist_folder_name = clean_line
        elif self._album_folder_name is None:
            self._album_folder_name = clean_line

        self._update_relative_album_path()

    def _extract_prefixed_name(self, clean_line):
        for prefix in self._CAPTURE_PREFIXES:
            if prefix not in clean_line:
                continue

            name = clean_line.split(prefix, 1)[1].strip()
            return name or None

        return None

    def _looks_like_folder_name(self, clean_line):
        if not clean_line:
            return False

        if clean_line.startswith(self._NON_FOLDER_PREFIXES):
            return False

        if "%" in clean_line or "press Enter to try again" in clean_line:
            return False

        return True

    def _update_relative_album_path(self):
        if not self._artist_folder_name or not self._album_folder_name:
            return

        self.relative_album_path = Path(
            self._artist_folder_name,
            self._album_folder_name,
        )

    def _finish(self, process):
        success = (not self._cancel_requested) and process.returncode == 0

        if self._cancel_requested:
            self.log_callback.emit("Download cancelled")
        elif success:
            self.log_callback.emit("Download finished")
        else:
            self.log_callback.emit("Download failed")

        if self.on_finished:
            self.on_finished(success)

    def cancel(self):
        with self._lock:
            self._cancel_requested = True

            if self.process and self.process.poll() is None:
                self._kill_process_tree(self.process)

    def _kill_process_tree(self, process):
        if process.poll() is not None:
            return

        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                )
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            pass
