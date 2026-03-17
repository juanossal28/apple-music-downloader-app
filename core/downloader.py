import subprocess
import threading


class DownloadTask:

    def __init__(self, link, log_callback, process_tracker=None):
        self.link = link
        self.log_callback = log_callback
        self.process_tracker = process_tracker
        self.process = None
        self._cancel_requested = False
        self._lock = threading.Lock()

    def start(self):
        thread = threading.Thread(target=self.run)
        thread.daemon = True
        thread.start()

    def cancel(self):
        self._cancel_requested = True

        with self._lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()

        self.log_callback.emit("[CANCELLED] Download cancelled")

    def run(self):

        retry_count = 0
        max_retries = 3

        with self._lock:
            self.process = subprocess.Popen(
                ["go", "run", "main.go", "--song", self.link],
                cwd="C:\\Users\\juano\\Documents\\Herramientas\\apple-music-downloader\\apple-music-downloader-main",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1
            )

            if self.process_tracker:
                self.process_tracker.track(self.process)

        while True:

            if self._cancel_requested:
                break

            line = self.process.stdout.readline()

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

            self.log_callback.emit(clean_line)

            if "press Enter to try again" in clean_line:

                if retry_count < max_retries:

                    self.log_callback.emit(
                        f"[AUTO RETRY] Attempt {retry_count + 1}/{max_retries}"
                    )

                    try:
                        self.process.stdin.write("\n")
                        self.process.stdin.flush()
                        retry_count += 1
                    except Exception:
                        pass
                else:
                    self.log_callback.emit(
                        "[AUTO RETRY] Max retries reached. Skipping..."
                    )

        if self.process:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

        if not self._cancel_requested:
            self.log_callback.emit("Download finished")
