import subprocess
import threading


class DownloadTask:

    def __init__(self, link, log_callback):
        self.link = link
        self.log_callback = log_callback

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
            bufsize=1
        )

        while True:

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

        self.log_callback.emit("Download finished")