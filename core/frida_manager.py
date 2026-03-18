import subprocess
import re

from core.paths import get_amd_workdir


class FridaManager:

    def __init__(self):

        self.device = "emulator-5554"
        self.frida_process = None

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

        workdir = str(get_amd_workdir())

        self.frida_process = subprocess.Popen(
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

    # -------------------------

    def is_agent_running(self):

        return (
            self.frida_process is not None
            and self.frida_process.poll() is None
        )

    # -------------------------

    def stop_agent(self):

        if self.frida_process and self.frida_process.poll() is None:
            self.frida_process.kill()

        self.frida_process = None
