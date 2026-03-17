import subprocess
import time
import os


class EmulatorManager:

    def __init__(self):

        self.adb = os.path.expandvars(
            r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
        )

        self.emulator = os.path.expandvars(
            r"%LOCALAPPDATA%\Android\Sdk\emulator\emulator.exe"
        )

        self.avd = "Pixel_3"
        self.emulator_process = None
        self.device = "emulator-5554"

    def _run_adb(self, args):

        return subprocess.run(
            [self.adb, "-s", self.device] + args,
            capture_output=True,
            text=True
        )

    def start(self):

        subprocess.run([self.adb, "start-server"])

        time.sleep(2)

        self.emulator_process = subprocess.Popen([
            self.emulator,
            "-avd",
            self.avd
        ])

    def stop(self):

        try:
            self._run_adb(["emu", "kill"])
        except Exception:
            pass

        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "qemu-system-x86_64.exe", "/T"],
                capture_output=True,
                text=True
            )
        except Exception:
            pass

        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "emulator.exe", "/T"],
                capture_output=True,
                text=True
            )
        except Exception:
            pass

        if self.emulator_process and self.emulator_process.poll() is None:
            self.emulator_process.kill()

        self.emulator_process = None
