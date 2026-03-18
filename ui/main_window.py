from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QLabel,
    QListWidget,
    QFileDialog,
    QMessageBox
)
import threading
import shutil
import json
from pathlib import Path

from core.downloader import DownloadTask
from ui.download_widget import DownloadWidget
from core.emulator import EmulatorManager
from core.frida_manager import FridaManager
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import Signal, Qt, QTimer
from core.apple_music_api import fetch_metadata
from core.system_cleanup import clean_go_build_subfolders
from core.paths import (
    get_project_root,
    get_amd_downloads_dir,
    get_download_destination_file,
    get_download_registry_file,
)


class MainWindow(QMainWindow):

    download_finished_signal = Signal(object, bool)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Apple Music Downloader")
        screen = QGuiApplication.primaryScreen()
        geometry = screen.availableGeometry()

        screen_width = geometry.width()
        screen_height = geometry.height()

        width = int(screen_width * 0.5)
        height = int(screen_height * 0.5)

        self.resize(width, height)

        self.emulator = EmulatorManager()
        self.frida = FridaManager()

        self.links_file = get_project_root() / "data" / "links.txt"

        self.max_simultaneous_downloads = 3
        self.pending_downloads = []
        self.active_tasks = []
        self.task_widgets = {}
        self.task_links = {}
        self.task_metadata = {}
        self.completed_successful = []
        self.download_destination_file = get_download_destination_file()
        self.download_registry_file = get_download_registry_file()
        self.download_destination = self.load_download_destination()
        self.download_registry = self.load_download_registry()

        self.emulator_state_timer = QTimer(self)
        self.emulator_state_timer.setInterval(1500)
        self.emulator_state_timer.timeout.connect(self.refresh_setup_buttons)

        central = QWidget()
        main_layout = QVBoxLayout()

        # -----------------------------
        # MAIN 3 COLUMN LAYOUT
        # -----------------------------

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(15)

        # =====================================================
        # COLUMN 1 (LEFT) - EMULATOR / FRIDA
        # =====================================================

        col_left = QVBoxLayout()

        required_title = QLabel("Required Setup")
        col_left.addWidget(required_title)

        # ----- BUTTON 1 -----
        self.emulator_button = QPushButton()
        btn1_layout = QHBoxLayout(self.emulator_button)
        btn1_layout.setContentsMargins(10, 0, 10, 0)

        num1 = QLabel("[1]")
        num1.setStyleSheet("color: gray; font-weight: bold;")
        text1 = QLabel("Start Emulator")

        btn1_layout.addWidget(num1)
        btn1_layout.addStretch()
        btn1_layout.addWidget(text1)

        col_left.addWidget(self.emulator_button)

        # ----- BUTTON 2 -----
        self.frida_button = QPushButton()
        btn2_layout = QHBoxLayout(self.frida_button)
        btn2_layout.setContentsMargins(10, 0, 10, 0)

        num2 = QLabel("[2]")
        num2.setStyleSheet("color: gray; font-weight: bold;")
        text2 = QLabel("Prepare Frida")

        btn2_layout.addWidget(num2)
        btn2_layout.addStretch()
        btn2_layout.addWidget(text2)

        col_left.addWidget(self.frida_button)

        col_left.addStretch()  # espacio para futuros botones

        columns_layout.addLayout(col_left, 1)

        # =====================================================
        # COLUMN 2 (CENTER) - LINKS
        # =====================================================

        col_center = QVBoxLayout()

        links_title = QLabel("Links")
        col_center.addWidget(links_title)

        buttons_row = QHBoxLayout()

        self.clipboard_button = QPushButton("Add from Clipboard")
        buttons_row.addWidget(self.clipboard_button)

        self.remove_button = QPushButton("Remove")
        buttons_row.addWidget(self.remove_button)

        col_center.addLayout(buttons_row)

        self.link_list = QListWidget()
        col_center.addWidget(self.link_list)

        columns_layout.addLayout(col_center, 2)

        # =====================================================
        # COLUMN 3 (RIGHT) - DOWNLOADS
        # =====================================================

        col_right = QVBoxLayout()

        downloads_title = QLabel("Downloads")
        col_right.addWidget(downloads_title)

        # BOTONES ROW (Start + Clear)
        buttons_row = QHBoxLayout()

        self.start_button = QPushButton("Start Downloads")
        buttons_row.addWidget(self.start_button)

        self.select_destination_button = QPushButton("Select Folder")
        buttons_row.addWidget(self.select_destination_button)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setStyleSheet("background-color: #c0392b; color: white;")
        buttons_row.addWidget(self.clear_button)

        col_right.addLayout(buttons_row)

        self.destination_label = QLabel(
            self._format_destination_label(self.download_destination)
        )
        self.destination_label.setWordWrap(True)
        self.destination_label.setStyleSheet("color: #7f8c8d;")
        col_right.addWidget(self.destination_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.download_container = QWidget()
        self.download_layout = QVBoxLayout()
        self.download_layout.setSpacing(10)
        self.download_layout.setAlignment(Qt.AlignTop)

        self.download_container.setLayout(self.download_layout)
        self.scroll.setWidget(self.download_container)

        col_right.addWidget(self.scroll)

        columns_layout.addLayout(col_right, 4)

        # -----------------------------

        main_layout.addLayout(columns_layout)

        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # conexiones
        self.emulator_button.clicked.connect(self.start_emulator)
        self.frida_button.clicked.connect(self.prepare_frida)
        self.clipboard_button.clicked.connect(self.add_from_clipboard)
        self.remove_button.clicked.connect(self.remove_link)
        self.start_button.clicked.connect(self.start_downloads)
        self.select_destination_button.clicked.connect(self.select_download_destination)
        self.clear_button.clicked.connect(self.clear_downloads)
        self.download_finished_signal.connect(self._on_task_finished)

        self.refresh_setup_buttons()
        self.emulator_state_timer.start()

        self.load_links()

    # -------------------------

    def _format_destination_label(self, destination):
        if destination:
            return f"Destination: {destination}"
        return "Destination: not selected"

    def load_download_destination(self):
        if not self.download_destination_file.exists():
            return None

        destination = self.download_destination_file.read_text(encoding="utf-8").strip()
        return destination or None

    def save_download_destination(self, destination):
        self.download_destination_file.write_text(destination, encoding="utf-8")

    def load_download_registry(self):
        if not self.download_registry_file.exists():
            return {}

        try:
            return json.loads(self.download_registry_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_download_registry(self):
        self.download_registry_file.write_text(
            json.dumps(self.download_registry, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _resolve_metadata(self, link, metadata=None):
        if metadata:
            return metadata

        for _ in range(2):
            resolved = fetch_metadata(link)
            if resolved:
                return resolved

        return None

    def select_download_destination(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select folder for completed downloads",
            self.download_destination or str(get_project_root())
        )

        if not selected:
            return

        self.download_destination = selected
        self.save_download_destination(selected)
        self.destination_label.setText(self._format_destination_label(selected))

    # -------------------------

    def load_links(self):

        if not self.links_file.exists():
            return

        with open(self.links_file, "r", encoding="utf-8") as f:
            links = f.readlines()

        for link in links:
            link = link.strip()
            if link:
                self.link_list.addItem(link)

    # -------------------------

    def save_links(self):

        links = []

        for i in range(self.link_list.count()):
            links.append(self.link_list.item(i).text())

        with open(self.links_file, "w", encoding="utf-8") as f:
            for link in links:
                f.write(link + "\n")

    # -------------------------

    def add_from_clipboard(self):

        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if not text:
            return

        lines = text.splitlines()

        added = 0

        for line in lines:
            link = line.strip()

            if not link:
                continue

            # evitar duplicados
            exists = False
            for i in range(self.link_list.count()):
                if self.link_list.item(i).text() == link:
                    exists = True
                    break

            if not exists:
                self.link_list.addItem(link)
                added += 1

        self.save_links()

    # -------------------------

    def remove_link(self):

        item = self.link_list.currentItem()

        if not item:
            return

        row = self.link_list.row(item)
        self.link_list.takeItem(row)

        self.save_links()

    # -------------------------

    def refresh_setup_buttons(self):

        emulator_running = self.emulator.is_emulator_running()
        emulator_booted = self.emulator.is_boot_completed()

        self.emulator_button.setEnabled(not emulator_running)
        self.frida_button.setEnabled(emulator_booted)

        self.update_start_button_state(emulator_running=emulator_running)

    def is_required_setup_ready(self, emulator_running=None):

        if emulator_running is None:
            emulator_running = self.emulator.is_emulator_running()

        return emulator_running and self.frida.is_agent_running()

    def update_start_button_state(self, emulator_running=None):

        setup_ready = self.is_required_setup_ready(emulator_running=emulator_running)
        downloads_in_progress = bool(self.active_tasks or self.pending_downloads)
        can_start = setup_ready and not downloads_in_progress

        self.start_button.setEnabled(can_start)

        if setup_ready:
            self.start_button.setToolTip("")
        else:
            self.start_button.setToolTip(
                "Primero inicializa todo en 'Required Setup' (Emulator + Frida Agent)."
            )

    # -------------------------

    def start_downloads(self):

        if not self.is_required_setup_ready():
            self.update_start_button_state()
            return

        if self.active_tasks or self.pending_downloads:
            return

        if not self.download_destination or not Path(self.download_destination).exists():
            QMessageBox.warning(
                self,
                "Destination required",
                "Select a destination folder before starting downloads."
            )
            return

        for i in range(self.link_list.count()):

            link = self.link_list.item(i).text()

            metadata = self._resolve_metadata(link)

            if metadata:

                track_name = metadata.get("track")
                artist = metadata.get("artist")
                album = metadata.get("album")

                title = (
                    f"<b>{track_name}</b><br>"
                    f"<span style='color:gray'>Artist:</span> {artist}<br>"
                    f"<span style='color:gray'>Album:</span> {album}"
                )

            else:
                title = link

            if self._is_already_downloaded(link, metadata):
                continue

            self.pending_downloads.append((link, title, metadata))

        if not self.pending_downloads:
            return

        self.update_start_button_state()
        self._start_next_downloads()

    # -------------------------

    def _start_next_downloads(self):

        while (
            len(self.active_tasks) < self.max_simultaneous_downloads
            and self.pending_downloads
        ):
            link, title, metadata = self.pending_downloads.pop(0)

            widget = DownloadWidget(title)
            self.download_layout.addWidget(widget)

            task = DownloadTask(
                link,
                widget.log_signal,
                on_finished=None
            )

            task.on_finished = (
                lambda success, current_task=task:
                self.download_finished_signal.emit(current_task, success)
            )

            self.task_widgets[task] = widget
            self.task_links[task] = link
            self.task_metadata[task] = metadata
            self.active_tasks.append(task)
            task.start()

    # -------------------------

    def _on_task_finished(self, task, success):

        if task in self.active_tasks:
            self.active_tasks.remove(task)

        widget = self.task_widgets.pop(task, None)
        link = self.task_links.pop(task, None)
        metadata = self.task_metadata.pop(task, None)

        if success and link:
            self.completed_successful.append((link, metadata))

        if success and widget:
            self.download_layout.removeWidget(widget)
            widget.deleteLater()

        self._start_next_downloads()

        if not self.active_tasks and not self.pending_downloads:
            self._move_completed_downloads()
            self._update_download_registry()
            self.update_start_button_state()

    def _move_completed_downloads(self):

        source_root = get_amd_downloads_dir()

        if not source_root.exists() or not self.download_destination:
            return

        destination_root = Path(self.download_destination)
        destination_root.mkdir(parents=True, exist_ok=True)

        for item in source_root.iterdir():

            if not item.is_dir():
                continue

            try:
                self._merge_or_move_dir(item, destination_root / item.name)
            except Exception:
                continue

    def _merge_or_move_dir(self, src_dir, dst_dir):

        if not dst_dir.exists():
            shutil.move(str(src_dir), str(dst_dir))
            return

        for child in src_dir.iterdir():
            dst_child = dst_dir / child.name

            if child.is_dir():
                self._merge_or_move_dir(child, dst_child)
            else:
                if not dst_child.exists():
                    shutil.move(str(child), str(dst_child))
                else:
                    try:
                        child.unlink()
                    except FileNotFoundError:
                        pass

        try:
            src_dir.rmdir()
        except OSError:
            pass

    def _is_already_downloaded(self, link, metadata):

        if self._is_download_record_valid(link):
            return True

        if not self.download_destination:
            return False

        resolved_metadata = self._resolve_metadata(link, metadata)

        if not resolved_metadata:
            return False

        artist = resolved_metadata.get("artist")
        album = resolved_metadata.get("album")

        if not artist or not album:
            return False

        album_path = Path(self.download_destination) / artist / album

        if not album_path.exists() or not album_path.is_dir():
            return False

        return any(p.is_file() for p in album_path.rglob("*"))

    def _is_download_record_valid(self, link):
        if not self.download_destination:
            return False

        relative = self.download_registry.get(link)

        if not relative:
            return False

        target = Path(self.download_destination) / relative
        return target.exists() and target.is_dir() and any(p.is_file() for p in target.rglob("*"))

    def _update_download_registry(self):
        if not self.completed_successful or not self.download_destination:
            self.completed_successful.clear()
            return

        for link, metadata in self.completed_successful:
            resolved_metadata = self._resolve_metadata(link, metadata)
            relative = self._metadata_to_relative_album_path(resolved_metadata)

            if not relative:
                continue

            target = Path(self.download_destination) / relative

            if target.exists() and target.is_dir() and any(p.is_file() for p in target.rglob("*")):
                self.download_registry[link] = relative

        self.completed_successful.clear()
        self.save_download_registry()

    def _metadata_to_relative_album_path(self, metadata):
        if not metadata:
            return None

        artist = metadata.get("artist")
        album = metadata.get("album")

        if not artist or not album:
            return None

        return f"{artist}/{album}"

    # -------------------------

    def start_emulator(self):

        self.emulator.start()
        self.refresh_setup_buttons()

    # -------------------------

    def prepare_frida(self):

        if not self.emulator.is_boot_completed():
            return

        thread = threading.Thread(target=self._prepare_frida_worker)
        thread.daemon = True
        thread.start()

    def _prepare_frida_worker(self):

        print("Stopping previous frida-server...")
        self.frida.stop_frida()

        print("Enabling root...")
        self.frida.enable_root()

        print("Disabling SELinux...")
        self.frida.disable_selinux()

        print("Starting frida-server...")
        self.frida.start_frida_server()

        print("Configuring TCP forward...")
        self.frida.forward_port()

        print("Finding Apple Music process...")

        pid = self.frida.get_apple_music_pid()

        if not pid:
            print("Apple Music process not found")
            return

        print(f"PID detected: {pid}")

        self.frida.attach_agent(pid)

        print("Frida agent attached")

    # -------------------------

    def clear_downloads(self):
        """Cancela descargas, limpia widgets y borra subcarpetas go-build."""

        self.pending_downloads.clear()

        for task in list(self.active_tasks):
            task.cancel()

        self.active_tasks.clear()
        self.task_widgets.clear()
        self.task_links.clear()
        self.task_metadata.clear()
        self.completed_successful.clear()

        while self.download_layout.count():
            item = self.download_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.update_start_button_state()
        clean_go_build_subfolders()

    def closeEvent(self, event):

        self.pending_downloads.clear()

        for task in list(self.active_tasks):
            task.cancel()

        self.active_tasks.clear()
        self.task_widgets.clear()
        self.task_links.clear()
        self.task_metadata.clear()
        self.completed_successful.clear()

        try:
            self.frida.stop_agent()
            self.frida.stop_frida()
        except Exception:
            pass

        try:
            self.emulator.stop()
        except Exception:
            pass

        clean_go_build_subfolders()

        super().closeEvent(event)
