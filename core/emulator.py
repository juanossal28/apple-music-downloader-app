import subprocess
import time
import os


class EmulatorManager:

    def __init__(self, process_tracker=None):

        self.adb = os.path.expandvars(
            r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
        )

        self.emulator = os.path.expandvars(
            r"%LOCALAPPDATA%\Android\Sdk\emulator\emulator.exe"
        )

        self.avd = "Pixel_3"
        self.process_tracker = process_tracker
        self.emulator_process = None

    def start(self):

        subprocess.run([self.adb, "start-server"])

        time.sleep(2)

        self.emulator_process = subprocess.Popen([
            self.emulator,
            "-avd",
            self.avd
        ])

        if self.process_tracker:
            self.process_tracker.track(self.emulator_process)

    def stop(self):

        if self.emulator_process and self.emulator_process.poll() is None:
            self.emulator_process.terminate()
            try:
                self.emulator_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.emulator_process.kill()

        subprocess.run([self.adb, "emu", "kill"], capture_output=True, text=True)
