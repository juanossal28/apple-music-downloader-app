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

    def start(self):

        subprocess.run([self.adb, "start-server"])

        time.sleep(2)

        subprocess.Popen([
            self.emulator,
            "-avd",
            self.avd
        ])