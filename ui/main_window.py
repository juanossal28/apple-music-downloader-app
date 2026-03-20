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
    QMessageBox,
)
import threading
import shutil
import re
import unicodedata
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
)


class MainWindow(QMainWindow):
    download_finished_signal = Signal(object, bool)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Apple Music Downloader")
        self._resize_to_screen()

        self.emulator = EmulatorManager()
        self.frida = FridaManager()

        self.links_file = get_project_root() / "data" / "links.txt"

        # Permitimos hasta 3 descargas simultáneas y movemos carpetas solo al finalizar el lote.
        self.max_simultaneous_downloads = 3
        self.pending_downloads = []
        self.active_tasks = []
        self.task_widgets = {}
        self.download_destination_file = get_download_destination_file()
        self.download_destination = self.load_download_destination()

        self.emulator_state_timer = QTimer(self)
        self.emulator_state_timer.setInterval(1500)
        self.emulator_state_timer.timeout.connect(self.refresh_setup_buttons)

        central = QWidget()
        main_layout = QVBoxLayout()

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(15)

        col_left = QVBoxLayout()

        required_title = QLabel("Required Setup")
        col_left.addWidget(required_title)

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
        col_left.addStretch()
        columns_layout.addLayout(col_left, 1)

        col_center = QVBoxLayout()

        links_title = QLabel("Links")
        col_center.addWidget(links_title)

        links_buttons_row = QHBoxLayout()

        self.clipboard_button = QPushButton("Add from Clipboard")
        links_buttons_row.addWidget(self.clipboard_button)

        self.remove_button = QPushButton("Remove")
        links_buttons_row.addWidget(self.remove_button)

        col_center.addLayout(links_buttons_row)

        self.link_list = QListWidget()
        col_center.addWidget(self.link_list)

        columns_layout.addLayout(col_center, 2)

        col_right = QVBoxLayout()

        downloads_title = QLabel("Downloads")
        col_right.addWidget(downloads_title)

        downloads_buttons_row = QHBoxLayout()

        self.start_button = QPushButton("Start Downloads")
        downloads_buttons_row.addWidget(self.start_button)

        self.select_destination_button = QPushButton("Select Folder")
        downloads_buttons_row.addWidget(self.select_destination_button)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setStyleSheet("background-color: #c0392b; color: white;")
        downloads_buttons_row.addWidget(self.clear_button)

        col_right.addLayout(downloads_buttons_row)

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

        main_layout.addLayout(columns_layout)
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        self.clipboard_button.clicked.connect(self.add_from_clipboard)
        self.remove_button.clicked.connect(self.remove_link)
        self.start_button.clicked.connect(self.start_downloads)
        self.clear_button.clicked.connect(self.clear_downloads)
        self.select_destination_button.clicked.connect(self.select_download_destination)
        self.emulator_button.clicked.connect(self.start_emulator)
        self.frida_button.clicked.connect(self.prepare_frida)
        self.download_finished_signal.connect(self._on_task_finished)

        self.load_links()
        self.refresh_setup_buttons()
        self.emulator_state_timer.start()

    def _resize_to_screen(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            self.resize(900, 600)
            return

        geometry = screen.availableGeometry()
        self.resize(int(geometry.width() * 0.5), int(geometry.height() * 0.5))

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

    def select_download_destination(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select folder for completed downloads",
            self.download_destination or str(get_project_root()),
        )

        if not selected:
            return

        self.download_destination = selected
        self.save_download_destination(selected)
        self.destination_label.setText(self._format_destination_label(selected))

    def load_links(self):
        if not self.links_file.exists():
            return

        for link in self.links_file.read_text(encoding="utf-8").splitlines():
            stripped_link = link.strip()
            if stripped_link:
                self.link_list.addItem(stripped_link)

    def save_links(self):
        links = [self.link_list.item(i).text() for i in range(self.link_list.count())]
        content = "\n".join(links)

        if content:
            content += "\n"

        self.links_file.write_text(content, encoding="utf-8")

    def add_from_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if not text:
            return

        existing_links = {
            self.link_list.item(i).text()
            for i in range(self.link_list.count())
        }

        for line in text.splitlines():
            link = line.strip()
            if not link or link in existing_links:
                continue

            self.link_list.addItem(link)
            existing_links.add(link)

        self.save_links()

    def remove_link(self):
        item = self.link_list.currentItem()
        if not item:
            return

        row = self.link_list.row(item)
        self.link_list.takeItem(row)
        self.save_links()

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
                "Select a destination folder before starting downloads.",
            )
            return

        for i in range(self.link_list.count()):
            link = self.link_list.item(i).text()
            metadata = fetch_metadata(link)

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

            if self._is_already_downloaded(metadata):
                continue

            self.pending_downloads.append((link, title))

        if not self.pending_downloads:
            return

        self.update_start_button_state()
        self._start_next_downloads()

    def _start_next_downloads(self):
        while (
            len(self.active_tasks) < self.max_simultaneous_downloads
            and self.pending_downloads
        ):
            link, title = self.pending_downloads.pop(0)

            widget = DownloadWidget(title)
            self.download_layout.addWidget(widget)

            task = DownloadTask(link, widget.log_signal, on_finished=None)
            task.on_finished = (
                lambda success, current_task=task:
                self.download_finished_signal.emit(current_task, success)
            )

            self.task_widgets[task] = widget
            self.active_tasks.append(task)
            task.start()

    def _on_task_finished(self, task, success):
        if task in self.active_tasks:
            self.active_tasks.remove(task)

        widget = self.task_widgets.pop(task, None)

        if success and widget:
            self.download_layout.removeWidget(widget)
            widget.deleteLater()

        self._start_next_downloads()

        if not self.active_tasks and not self.pending_downloads:
            self._move_completed_downloads()
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
            elif not dst_child.exists():
                shutil.move(str(child), str(dst_child))

        try:
            src_dir.rmdir()
        except OSError:
            pass

    def _sanitize_fs_name(self, value):
        if not value:
            return ""

        sanitized = re.sub(r'[<>:"/\\|?*]', "_", str(value)).strip()
        return sanitized.rstrip(". ")

    def _normalize_name(self, value):
        if not value:
            return ""

        normalized = unicodedata.normalize("NFKD", str(value))
        normalized = "".join(
            char for char in normalized if not unicodedata.combining(char)
        )
        normalized = self._sanitize_fs_name(normalized).casefold()
        return re.sub(r'[^a-z0-9]+', "", normalized)

    def _iter_matching_dirs(self, parent_dir, expected_name):
        if not parent_dir.exists() or not parent_dir.is_dir() or not expected_name:
            return []

        expected_normalized = self._normalize_name(expected_name)
        matches = []

        for child in parent_dir.iterdir():
            if not child.is_dir():
                continue

            child_normalized = self._normalize_name(child.name)
            if child_normalized == expected_normalized:
                matches.append(child)

        return matches

    def _album_contains_track(self, album_path, track_name):
        media_extensions = {".m4a", ".mp4", ".flac", ".alac", ".aac", ".wav", ".mp3"}
        track_normalized = self._normalize_name(track_name)

        for path in album_path.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in media_extensions:
                continue

            if not track_normalized:
                return True

            if track_normalized in self._normalize_name(path.stem):
                return True

        return False

    def _is_already_downloaded(self, metadata):
        if not metadata or not self.download_destination:
            return False

        artist = metadata.get("artist")
        album = metadata.get("album")
        track = metadata.get("track")

        if not artist or not album:
            return False

        destination_root = Path(self.download_destination)
        if not destination_root.exists() or not destination_root.is_dir():
            return False

        artist_dirs = self._iter_matching_dirs(destination_root, artist)
        if not artist_dirs:
            fallback_artist_dir = destination_root / self._sanitize_fs_name(artist)
            if fallback_artist_dir.exists() and fallback_artist_dir.is_dir():
                artist_dirs = [fallback_artist_dir]

        for artist_dir in artist_dirs:
            album_dirs = self._iter_matching_dirs(artist_dir, album)
            if not album_dirs:
                fallback_album_dir = artist_dir / self._sanitize_fs_name(album)
                if fallback_album_dir.exists() and fallback_album_dir.is_dir():
                    album_dirs = [fallback_album_dir]

            for album_dir in album_dirs:
                if self._album_contains_track(album_dir, track):
                    return True

        return False

    def start_emulator(self):
        self.emulator.start()
        self.refresh_setup_buttons()

    def prepare_frida(self):
        if not self.emulator.is_boot_completed():
            return

        thread = threading.Thread(target=self._prepare_frida_worker, daemon=True)
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

    def _cancel_all_tasks(self):
        self.pending_downloads.clear()

        for task in list(self.active_tasks):
            task.cancel()

        self.active_tasks.clear()
        self.task_widgets.clear()

    def _clear_download_widgets(self):
        while self.download_layout.count():
            item = self.download_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def clear_downloads(self):
        """Cancela descargas, limpia widgets y borra subcarpetas go-build."""
        self._cancel_all_tasks()
        self._clear_download_widgets()
        self.update_start_button_state()
        clean_go_build_subfolders()

    def closeEvent(self, event):
        self._cancel_all_tasks()

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
