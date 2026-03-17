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
        self.device = "emulator-5554"
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

        # Cierre limpio del emulador Android (más confiable que matar solo el launcher).
        subprocess.run(
            [self.adb, "-s", self.device, "emu", "kill"],
            capture_output=True,
            text=True
        )

        if self.emulator_process and self.emulator_process.poll() is None:
            self.emulator_process.kill()

        # fallback para asegurar cierre de procesos del emulador en Windows
        subprocess.run(
            ["taskkill", "/IM", "qemu-system-x86_64.exe", "/F"],
            capture_output=True,
            text=True
        )
        subprocess.run(
            ["taskkill", "/IM", "emulator.exe", "/F"],
            capture_output=True,
            text=True
        )

        self.emulator_process = None
