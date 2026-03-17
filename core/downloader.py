import subprocess
import threading
import os
import signal


class DownloadTask:

    def __init__(self, link, log_callback):
        self.link = link
        self.log_callback = log_callback
        self.process = None
        self._cancel_requested = False
        self._lock = threading.Lock()

    def start(self):
        thread = threading.Thread(target=self.run)
        thread.daemon = True
        thread.start()

    def run(self):

        retry_count = 0
        max_retries = 3

        process = subprocess.Popen(
            ["go", "run", "main.go", "--song", self.link],
            cwd="C:\\Users\\juano\\Documents\\Herramientas\\apple-music-downloader\\apple-music-downloader-main",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        )

        with self._lock:
            self.process = process

            if self._cancel_requested:
                self._kill_process_tree(process)

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

            # -------------------------
            # PROGRESO DOWNLOAD
            # -------------------------
            if clean_line.startswith("Downloading"):
                try:
                    percent = clean_line.split("%")[0].split()[-1]
                    self.log_callback.emit(f"[PROGRESS] Downloading... {percent}%")
                except:
                    pass
                continue

            # -------------------------
            # PROGRESO DECRYPT
            # -------------------------
            if clean_line.startswith("Decrypting"):
                try:
                    percent = clean_line.split("%")[0].split()[-1]
                    self.log_callback.emit(f"[PROGRESS] Decrypting... {percent}%")
                except:
                    pass
                continue

            self.log_callback.emit(clean_line)

            # -------------------------
            # AUTO RETRY
            # -------------------------
            if "press Enter to try again" in clean_line:

                if retry_count < max_retries:

                    self.log_callback.emit(
                        f"[AUTO RETRY] Attempt {retry_count + 1}/{max_retries}"
                    )

                    try:
                        process.stdin.write("\n")
                        process.stdin.flush()
                        retry_count += 1
                    except:
                        pass
                else:
                    self.log_callback.emit(
                        "[AUTO RETRY] Max retries reached. Skipping..."
                    )

        process.wait()

        if self._cancel_requested:
            self.log_callback.emit("Download cancelled")
        else:
            self.log_callback.emit("Download finished")

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
                    text=True
                )
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            pass
