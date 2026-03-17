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

    def start(self):

        subprocess.run([self.adb, "start-server"])

        time.sleep(2)

        self.emulator_process = subprocess.Popen([
            self.emulator,
            "-avd",
            self.avd
        ])

    def stop(self):

        if self.emulator_process and self.emulator_process.poll() is None:
            self.emulator_process.kill()

        self.emulator_process = None
