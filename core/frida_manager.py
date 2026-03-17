import subprocess
import re


class FridaManager:

    def __init__(self):

        self.device = "emulator-5554"

    def run_adb(self, args):

        return subprocess.run(
            ["adb", "-s", self.device] + args,
            capture_output=True,
            text=True
        )

    # -------------------------

    def stop_frida(self):

        self.run_adb(["shell", "pkill", "frida-server"])

    # -------------------------

    def enable_root(self):

        subprocess.run(["adb", "-s", self.device, "root"])

    # -------------------------

    def disable_selinux(self):

        self.run_adb(["shell", "setenforce", "0"])

    # -------------------------

    def start_frida_server(self):

        subprocess.Popen([
            "adb",
            "-s",
            self.device,
            "shell",
            "cd /data/local/tmp && ./frida-server &"
        ])

    # -------------------------

    def forward_port(self):

        subprocess.run(["adb", "-s", self.device, "forward", "--remove-all"])

        subprocess.run([
            "adb",
            "-s",
            self.device,
            "forward",
            "tcp:10020",
            "tcp:10020"
        ])

    # -------------------------

    def get_apple_music_pid(self):

        result = subprocess.check_output(
            ["adb", "-s", self.device, "shell", "ps"],
            text=True
        )

        for line in result.splitlines():

            if "com.apple.android.music" in line:

                fields = re.split(r"\s+", line.strip())

                return fields[1]

        return None

    # -------------------------

    def attach_agent(self, pid):

        workdir = r"C:\Users\juano\Documents\Herramientas\apple-music-downloader\apple-music-downloader-main"

        subprocess.Popen(
            [
                "frida",
                "-D",
                self.device,
                "-l",
                "agent.js",
                pid
            ],
            cwd=workdir
        )