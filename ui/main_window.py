from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QScrollArea,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QMessageBox,
    QTabWidget,
    QSizePolicy,
    QToolButton,
    QCheckBox,
    QStyle,
    QFrame,
)
import threading
import shutil
import re
from pathlib import Path

from core.downloader import DownloadTask
from ui.download_widget import DownloadWidget
from ui.loading_overlay import LoadingDialog
from core.emulator import EmulatorManager
from core.frida_manager import FridaManager
from PySide6.QtGui import QColor, QGuiApplication, QIcon
from PySide6.QtGui import QPainter
from PySide6.QtCore import QObject, QEvent, QRectF, QThread, Signal, QSize, Qt, QTimer
from core.apple_music_api import extract_ids, fetch_metadata
from core.download_registry import (
    build_download_key,
    build_relative_download_path,
    load_download_registry,
    normalize_for_match,
    read_downloader_config,
    save_download_registry,
)
from core.system_cleanup import clean_go_build_subfolders
from core.paths import (
    get_project_root,
    get_amd_config_file,
    get_amd_downloads_dir,
    get_download_destination_file,
    get_download_registry_file,
    get_emulator_launch_mode_file,
)


def build_download_title(link, metadata):
    if not metadata:
        return link

    track_name = metadata.get("track")
    artist = metadata.get("artist")
    album = metadata.get("album")
    return (
        f"<b>{track_name}</b><br>"
        f"<span style='color:gray'>Artist:</span> {artist}<br>"
        f"<span style='color:gray'>Album:</span> {album}"
    )


def find_existing_download_relative_path(
    download_destination,
    download_registry,
    downloader_config,
    link,
    metadata,
    allow_computed_without_registry=False,
):
    if not download_destination:
        return None

    destination_root = Path(download_destination)
    registry_key = build_download_key(link)
    candidate_paths = []

    stored_entry = download_registry.get(registry_key) or {}
    stored_relative_path = stored_entry.get("relative_path")
    if stored_relative_path:
        candidate_paths.append(Path(stored_relative_path))

    computed_relative_path = build_relative_download_path(metadata, downloader_config)
    should_try_computed_path = stored_relative_path or allow_computed_without_registry
    if computed_relative_path is not None and should_try_computed_path:
        candidate_paths.append(computed_relative_path)

    seen_paths = set()
    for candidate_path in candidate_paths:
        candidate_key = candidate_path.as_posix()
        if candidate_key in seen_paths:
            continue

        seen_paths.add(candidate_key)
        full_path = destination_root / candidate_path
        if not full_path.exists() or not full_path.is_dir():
            continue

        if any(path.is_file() for path in full_path.rglob("*")):
            return candidate_path

    for candidate_path in candidate_paths:
        fuzzy_path = find_fuzzy_matching_relative_path(destination_root, candidate_path)
        if fuzzy_path is None:
            continue

        full_path = destination_root / fuzzy_path
        if any(path.is_file() for path in full_path.rglob("*")):
            return fuzzy_path

    return None


def find_fuzzy_matching_relative_path(destination_root, relative_path):
    parts = list(relative_path.parts)
    if not parts:
        return None

    if len(parts) == 1:
        matched_album = find_matching_child_dir(destination_root, parts[0])
        if matched_album is None:
            return None
        return Path(matched_album.name)

    if len(parts) != 2:
        return None

    matched_artist = find_matching_child_dir(destination_root, parts[0])
    if matched_artist is None:
        return None

    matched_album = find_matching_child_dir(matched_artist, parts[1])
    if matched_album is None:
        return None

    return Path(matched_artist.name) / matched_album.name


def find_matching_child_dir(parent_dir, expected_name):
    expected_key = normalize_for_match(expected_name)
    if not expected_key or not parent_dir.exists():
        return None

    matches = []
    for child in parent_dir.iterdir():
        if not child.is_dir():
            continue

        child_key = normalize_for_match(child.name)
        if child_key == expected_key:
            matches.append(child)

    if len(matches) == 1:
        return matches[0]

    return None


def upsert_download_registry_entry(download_registry, link, metadata, relative_path):
    registry_key = build_download_key(link)
    entry = {
        "link": link,
        "relative_path": relative_path.as_posix(),
    }

    if metadata:
        entry["artist"] = metadata.get("artist")
        entry["album"] = metadata.get("album")

    if download_registry.get(registry_key) == entry:
        return False

    download_registry[registry_key] = entry
    return True


def is_already_downloaded(download_destination, download_registry, downloader_config, link, metadata):
    if not download_destination:
        return False

    registry_key = build_download_key(link)
    allow_computed_without_registry = registry_key.startswith("album:")
    relative_path = find_existing_download_relative_path(
        download_destination,
        download_registry,
        downloader_config,
        link,
        metadata,
        allow_computed_without_registry=allow_computed_without_registry,
    )
    if relative_path is not None:
        upsert_download_registry_entry(download_registry, link, metadata, relative_path)
        return True

    if registry_key in download_registry:
        download_registry.pop(registry_key, None)

    return False


class DownloadPreparationWorker(QObject):
    finished = Signal(object, int, object)
    failed = Signal(str)

    def __init__(self, links, download_destination, download_registry, downloader_config):
        super().__init__()
        self.links = links
        self.download_destination = download_destination
        self.download_registry = dict(download_registry)
        self.downloader_config = dict(downloader_config)
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            pending_downloads = []
            already_downloaded_count = 0

            for link in self.links:
                if self._cancel_requested:
                    return

                metadata = fetch_metadata(link)
                title = build_download_title(link, metadata)

                if is_already_downloaded(
                    self.download_destination,
                    self.download_registry,
                    self.downloader_config,
                    link,
                    metadata,
                ):
                    already_downloaded_count += 1
                    continue

                pending_downloads.append(
                    {
                        "link": link,
                        "title": title,
                        "metadata": metadata,
                    }
                )

            if not self._cancel_requested:
                self.finished.emit(
                    pending_downloads,
                    already_downloaded_count,
                    self.download_registry,
                )
        except Exception as exc:
            self.failed.emit(str(exc))


class LinkListItemWidget(QWidget):
    copy_requested = Signal(str)
    row_clicked = Signal()

    def __init__(self, link, copy_icon, parent=None):
        super().__init__(parent)
        self.link = link
        self.setObjectName("linkRow")

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 2, 8, 2)
        layout.setSpacing(8)

        self.id_label = QLabel(extract_display_link_id(link))
        self.id_label.setObjectName("linkIdLabel")
        self.id_label.setToolTip(link)
        self.id_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.id_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.copy_button = QToolButton()
        self.copy_button.setObjectName("copyLinkButton")
        if copy_icon.isNull():
            self.copy_button.setText("Copy")
        else:
            self.copy_button.setIcon(copy_icon)
            self.copy_button.setIconSize(QSize(20, 20))
        self.copy_button.setFixedSize(QSize(28, 28))
        self.copy_button.setToolTip("Copy full link")
        self.copy_button.setCursor(Qt.PointingHandCursor)
        self.copy_button.clicked.connect(lambda: self.copy_requested.emit(self.link))

        layout.addWidget(self.id_label)
        layout.addWidget(self.copy_button, alignment=Qt.AlignVCenter)
        self.setLayout(layout)

        self.setStyleSheet("""
        #linkIdLabel {
            color: #eef3fb;
            font-size: 9pt;
            font-weight: 600;
            background: transparent;
        }

        #copyLinkButton {
            background: transparent;
            border: none;
            color: #dbe7f6;
            font-size: 8pt;
            font-weight: 600;
            min-width: 28px;
            min-height: 28px;
            max-width: 28px;
            max-height: 28px;
            padding: 0px;
            border-radius: 6px;
        }

        #copyLinkButton:hover {
            background-color: rgba(95, 154, 232, 0.16);
        }
        """)

    def set_selected(self, selected):
        if selected:
            self.setStyleSheet("""
            #linkRow {
                background-color: rgba(63, 97, 145, 0.55);
                border-radius: 8px;
            }

            #linkIdLabel {
                color: #ffffff;
                font-size: 9pt;
                font-weight: 600;
                background: transparent;
            }

            #copyLinkButton {
                background: transparent;
                border: none;
                color: #ffffff;
                font-size: 8pt;
                font-weight: 600;
                min-width: 28px;
                min-height: 28px;
                max-width: 28px;
                max-height: 28px;
                padding: 0px;
                border-radius: 6px;
            }

            #copyLinkButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
            }
            """)
        else:
            self.setStyleSheet("""
            #linkRow {
                background: transparent;
                border-radius: 8px;
            }

            #linkIdLabel {
                color: #eef3fb;
                font-size: 9pt;
                font-weight: 600;
                background: transparent;
            }

            #copyLinkButton {
                background: transparent;
                border: none;
                color: #dbe7f6;
                font-size: 8pt;
                font-weight: 600;
                min-width: 28px;
                min-height: 28px;
                max-width: 28px;
                max-height: 28px;
                padding: 0px;
                border-radius: 6px;
            }

            #copyLinkButton:hover {
                background-color: rgba(95, 154, 232, 0.16);
            }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.row_clicked.emit()
        super().mousePressEvent(event)


class ToggleSwitch(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setContentsMargins(0, 0, 0, 0)
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def sizeHint(self):
        label_width = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(44 + label_width, 24)

    def paintEvent(self, event):
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        track_width = 34
        track_height = 18
        knob_size = 14
        label_gap = 10

        track_rect = QRectF(
            0,
            (self.height() - track_height) / 2,
            track_width,
            track_height,
        )

        if self.isEnabled():
            track_color = QColor("#4f9ef8") if self.isChecked() else QColor("#242a32")
            border_color = QColor("#4f9ef8") if self.isChecked() else QColor("#3b4350")
            knob_color = QColor("#f5f8fc") if self.isChecked() else QColor("#b7c0cb")
            text_color = QColor("#eef3fb") if self.isChecked() else QColor("#c8d3e0")
        else:
            track_color = QColor("#1d2127")
            border_color = QColor("#2b3138")
            knob_color = QColor("#7b8490")
            text_color = QColor("#6b7380")

        painter.setPen(border_color)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, track_height / 2, track_height / 2)

        knob_x = (
            track_rect.right() - knob_size - 2
            if self.isChecked()
            else track_rect.left() + 2
        )
        knob_rect = QRectF(
            knob_x,
            track_rect.top() + 2,
            knob_size,
            knob_size,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(knob_rect)

        text_rect = QRectF(
            track_rect.right() + label_gap,
            0,
            max(0, self.width() - track_width - label_gap),
            self.height(),
        )
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())


def extract_display_link_id(link):
    track_id, album_id = extract_ids(link)
    return track_id or album_id or link


def load_copy_link_icon():
    icon_path = get_project_root() / "ui" / "icons" / "copy-24.png"
    icon = QIcon(str(icon_path))
    if not icon.isNull():
        return icon

    style = QApplication.style()
    if style is not None:
        return style.standardIcon(QStyle.SP_FileDialogDetailedView)

    return QIcon()


class MainWindow(QMainWindow):
    download_finished_signal = Signal(object, bool)
    frida_preparation_finished = Signal(bool, str)
    APPLE_MUSIC_LINK_PATTERN = re.compile(
        r"^https://(?:beta\.music|music|classical\.music)\.apple\.com/"
        r"[a-zA-Z]{2}/(?:album|song|playlist|station|artist|music-video)/.+$"
    )

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
        self.failed_downloads = []
        self.download_destination_file = get_download_destination_file()
        self.download_registry_file = get_download_registry_file()
        self.emulator_launch_mode_file = get_emulator_launch_mode_file()
        self.download_registry = load_download_registry(self.download_registry_file)
        self.downloader_config = read_downloader_config(get_amd_config_file())
        self.successful_downloads = []
        self.download_destination = self.load_download_destination()
        self.emulator_launch_hidden = self.load_emulator_launch_hidden_preference()
        self.preparation_thread = None
        self.preparation_worker = None
        self.preparation_in_progress = False
        self.emulator_start_in_progress = False
        self.frida_preparation_in_progress = False
        self.loading_state = None
        self.loading_dialog = LoadingDialog(
            "Preparing Downloads",
            "Building the download queue. This can take a moment...",
            self,
        )
        self.copy_link_icon = load_copy_link_icon()

        self.emulator_state_timer = QTimer(self)
        self.emulator_state_timer.setInterval(1500)
        self.emulator_state_timer.timeout.connect(self.refresh_setup_buttons)

        central = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(16)

        col_left = QVBoxLayout()
        col_left.setSpacing(10)

        required_title = QLabel("Required Setup")
        required_title.setObjectName("sectionTitle")
        col_left.addWidget(required_title)

        self.emulator_button = self._create_setup_button("[1]", "Start Emulator")
        col_left.addWidget(self.emulator_button)

        self.emulator_hidden_switch = ToggleSwitch("Launch hidden")
        self.emulator_hidden_switch.setObjectName("headlessSwitch")
        self.emulator_hidden_switch.setChecked(self.emulator_launch_hidden)
        col_left.addWidget(self.emulator_hidden_switch, alignment=Qt.AlignHCenter)

        self.setup_divider = QFrame()
        self.setup_divider.setObjectName("setupDivider")
        self.setup_divider.setFrameShape(QFrame.HLine)
        self.setup_divider.setFrameShadow(QFrame.Plain)
        col_left.addWidget(self.setup_divider)

        self.frida_button = self._create_setup_button("[2]", "Prepare Frida")
        col_left.addWidget(self.frida_button)
        col_left.addStretch()
        columns_layout.addLayout(col_left, 5)

        col_center = QVBoxLayout()
        col_center.setSpacing(10)

        links_title = QLabel("Links")
        links_title.setObjectName("sectionTitle")
        col_center.addWidget(links_title)

        links_buttons_grid = QGridLayout()
        links_buttons_grid.setHorizontalSpacing(8)
        links_buttons_grid.setVerticalSpacing(8)

        self.clipboard_button = QPushButton("Add from Clipboard")
        links_buttons_grid.addWidget(self.clipboard_button, 0, 0)

        self.load_file_button = QPushButton("Load from File")
        links_buttons_grid.addWidget(self.load_file_button, 0, 1)

        self.remove_button = QPushButton("Remove")
        links_buttons_grid.addWidget(self.remove_button, 1, 0)

        self.clear_links_button = QPushButton("Clear All")
        links_buttons_grid.addWidget(self.clear_links_button, 1, 1)

        col_center.addLayout(links_buttons_grid)

        self.link_list = QListWidget()
        col_center.addWidget(self.link_list)

        columns_layout.addLayout(col_center, 9)

        col_right = QVBoxLayout()
        col_right.setSpacing(10)

        downloads_title = QLabel("Downloads")
        downloads_title.setObjectName("sectionTitle")
        col_right.addWidget(downloads_title)

        downloads_buttons_row = QHBoxLayout()
        downloads_buttons_row.setSpacing(8)

        self.start_button = QPushButton("Start Downloads")
        downloads_buttons_row.addWidget(self.start_button)

        self.select_destination_button = QPushButton("Select Folder")
        downloads_buttons_row.addWidget(self.select_destination_button)

        self.clear_button = QPushButton("Cancel && Clear Cache")
        downloads_buttons_row.addWidget(self.clear_button)

        col_right.addLayout(downloads_buttons_row)

        self.destination_label = QLabel(
            self._format_destination_label(self.download_destination)
        )
        self.destination_label.setWordWrap(True)
        self.destination_label.setStyleSheet("color: #7f8c8d;")
        col_right.addWidget(self.destination_label)

        self.download_tabs = QTabWidget()
        self.active_scroll, self.active_download_layout = self._create_download_tab()
        self.success_scroll, self.success_download_layout = self._create_download_tab()
        self.error_scroll, self.error_download_layout = self._create_download_tab()

        self.download_tabs.addTab(self.active_scroll, "")
        self.download_tabs.addTab(self.success_scroll, "")
        self.download_tabs.addTab(self.error_scroll, "")
        self.remaining_label = QLabel("Remaining: 0")
        self.remaining_label.setObjectName("remainingLabel")
        self.remaining_corner = QWidget()
        self.remaining_corner.setFixedHeight(30)
        remaining_corner_layout = QHBoxLayout()
        remaining_corner_layout.setContentsMargins(0, 0, 8, 4)
        remaining_corner_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        remaining_corner_layout.addWidget(self.remaining_label, alignment=Qt.AlignVCenter)
        self.remaining_corner.setLayout(remaining_corner_layout)
        self.download_tabs.setCornerWidget(self.remaining_corner, Qt.TopRightCorner)
        self._refresh_download_tab_labels()

        col_right.addWidget(self.download_tabs)
        columns_layout.addLayout(col_right, 14)

        main_layout.addLayout(columns_layout)
        central.setLayout(main_layout)
        self.setCentralWidget(central)
        self._apply_window_styles()

        self.clipboard_button.clicked.connect(self.add_from_clipboard)
        self.load_file_button.clicked.connect(self.load_links_from_file)
        self.remove_button.clicked.connect(self.remove_link)
        self.clear_links_button.clicked.connect(self.clear_all_links)
        self.start_button.clicked.connect(self.start_downloads)
        self.clear_button.clicked.connect(self.clear_downloads)
        self.select_destination_button.clicked.connect(self.select_download_destination)
        self.emulator_button.clicked.connect(self.start_emulator)
        self.emulator_hidden_switch.toggled.connect(self.set_emulator_launch_hidden_preference)
        self.frida_button.clicked.connect(self.prepare_frida)
        self.download_finished_signal.connect(self._on_task_finished)
        self.frida_preparation_finished.connect(self._on_frida_preparation_finished)
        self.link_list.itemSelectionChanged.connect(self.update_links_buttons_state)
        QApplication.instance().installEventFilter(self)

        self.load_links()
        self.update_links_buttons_state()
        self.refresh_setup_buttons()
        self.emulator_state_timer.start()

    def _create_setup_button(self, step_label, button_text):
        button = QPushButton()
        button.setObjectName("setupButton")
        button.setMinimumHeight(58)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(button)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        number_label = QLabel(step_label)
        number_label.setObjectName("setupStep")
        number_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        number_label.setFixedWidth(26)

        text_label = QLabel(button_text)
        text_label.setObjectName("setupText")
        text_label.setWordWrap(True)
        text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addWidget(number_label)
        layout.addWidget(text_label)
        button.step_label = number_label
        button.text_label = text_label
        return button

    def _apply_window_styles(self):
        self.setStyleSheet("""
        QMainWindow {
            background-color: #171a1f;
        }

        #sectionTitle {
            color: #f4f7fb;
            font-size: 10pt;
            font-weight: 700;
            letter-spacing: 0.02em;
            padding-bottom: 2px;
        }

        QPushButton {
            background-color: #242930;
            color: #f1f5fb;
            border: 1px solid #343a43;
            border-radius: 8px;
            min-height: 34px;
            padding: 0 14px;
        }

        QPushButton:hover:enabled {
            background-color: #2b313a;
            border-color: #4b7fc7;
        }

        QPushButton:disabled {
            color: #707782;
            background-color: #1d2127;
            border-color: #2b3138;
        }

        #setupButton {
            text-align: left;
            padding: 0;
            background-color: #20242b;
            border: 1px solid #313844;
            border-radius: 10px;
        }

        #setupButton:hover:enabled {
            background-color: #262b34;
            border-color: #4f9ef8;
        }

        #setupStep {
            color: #8ea4c0;
            font-size: 9pt;
            font-weight: 700;
            background: transparent;
        }

        #setupText {
            color: #f4f7fb;
            font-size: 9pt;
            font-weight: 600;
            background: transparent;
        }

        #setupStep:disabled, #setupText:disabled {
            color: #6b7380;
        }

        #headlessSwitch {
            font-size: 8pt;
            padding-left: 4px;
        }

        #setupDivider {
            border: none;
            background-color: rgba(116, 132, 154, 0.28);
            min-height: 1px;
            max-height: 1px;
            margin: 2px 6px 2px 6px;
        }

        QListWidget, QScrollArea {
            background-color: #1d2025;
            border: 1px solid #323842;
            border-radius: 10px;
        }

        QTabWidget::pane {
            background-color: #1d2025;
            border: 1px solid #323842;
            border-top-left-radius: 0px;
            border-top-right-radius: 10px;
            border-bottom-left-radius: 10px;
            border-bottom-right-radius: 10px;
        }

        QListWidget {
            padding: 6px;
            color: #f1f5fb;
            outline: none;
            show-decoration-selected: 0;
        }

        QListWidget::item {
            padding: 0 6px;
            border-radius: 6px;
            outline: none;
        }

        QListWidget::item:selected {
            background-color: #2f4f76;
            color: #ffffff;
            border: none;
            outline: none;
        }

        QTabBar::tab {
            background-color: #22262d;
            color: #c8d0da;
            border: 1px solid #323842;
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            padding: 8px 14px;
            margin-right: 4px;
        }

        QTabBar::tab:selected {
            background-color: #2a3038;
            color: #ffffff;
        }

        QTabWidget::right-corner {
            subcontrol-origin: margin;
            subcontrol-position: top right;
            right: 8px;
            top: -10px;
        }

        #remainingLabel {
            color: #9ca3af;
            font-size: 9pt;
            padding: 0;
            margin: 0;
        }
        """)

    def _create_download_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)
        container.setLayout(layout)

        scroll.setWidget(container)
        return scroll, layout

    def _refresh_download_tab_labels(self):
        self.download_tabs.setTabText(0, f"Active ({self.active_download_layout.count()})")
        self.download_tabs.setTabText(1, f"Successful ({self.success_download_layout.count()})")
        self.download_tabs.setTabText(2, f"Errors ({self.error_download_layout.count()})")
        self.remaining_label.setText(f"Remaining: {len(self.active_tasks) + len(self.pending_downloads)}")

    def _show_loading_overlay(self, state, title, message):
        self.loading_state = state
        self.loading_dialog.set_content(title, message)
        self.loading_dialog.show()

    def _hide_loading_overlay(self, state=None):
        if state is not None and self.loading_state != state:
            return

        self.loading_dialog.hide()
        self.loading_state = None

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

    def load_emulator_launch_hidden_preference(self):
        if not self.emulator_launch_mode_file.exists():
            return True

        try:
            return self.emulator_launch_mode_file.read_text(encoding="utf-8").strip().lower() != "window"
        except OSError:
            return True

    def save_download_destination(self, destination):
        self.download_destination_file.write_text(destination, encoding="utf-8")

    def set_emulator_launch_hidden_preference(self, hidden):
        self.emulator_launch_hidden = bool(hidden)
        try:
            mode = "hidden" if self.emulator_launch_hidden else "window"
            self.emulator_launch_mode_file.write_text(mode, encoding="utf-8")
        except OSError:
            pass

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
                self._add_link_list_item(stripped_link)

    def save_links(self):
        links = [
            self._get_link_list_item_link(self.link_list.item(i))
            for i in range(self.link_list.count())
        ]
        content = "\n".join(links)

        if content:
            content += "\n"

        self.links_file.write_text(content, encoding="utf-8")

    def add_from_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if not text:
            return

        self._add_links_from_lines(text.splitlines(), source_name="clipboard")

    def remove_link(self):
        selected_items = self.link_list.selectedItems()
        item = selected_items[0] if selected_items else None
        if not item:
            return

        row = self.link_list.row(item)
        self.link_list.takeItem(row)
        self.save_links()
        self.update_links_buttons_state()

    def clear_all_links(self):
        if self.link_list.count() == 0:
            return

        self.link_list.clear()
        self.save_links()
        self.update_links_buttons_state()

    def load_links_from_file(self):
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select link list file",
            str(get_project_root()),
            "Text Files (*.txt);;All Files (*)",
        )

        if not selected_file:
            return

        try:
            file_lines = Path(selected_file).read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            QMessageBox.warning(
                self,
                "Invalid file",
                "The selected file must be a UTF-8 text file.",
            )
            return
        except OSError as exc:
            QMessageBox.warning(
                self,
                "File error",
                f"Could not read the selected file:\n{exc}",
            )
            return

        self._add_links_from_lines(file_lines, source_name=Path(selected_file).name)

    def update_links_buttons_state(self):
        has_links = self.link_list.count() > 0
        has_selection = bool(self.link_list.selectedItems())

        self.remove_button.setEnabled(has_links and has_selection)
        self.clear_links_button.setEnabled(has_links)
        self._sync_link_item_selection_state()

    def _add_links_from_lines(self, lines, source_name):
        existing_links = {
            self._get_link_list_item_link(self.link_list.item(i))
            for i in range(self.link_list.count())
        }
        valid_links = []
        invalid_lines = []

        for raw_line in lines:
            link = raw_line.strip()
            if not link:
                continue

            if not self._is_valid_apple_music_link(link):
                invalid_lines.append(link)
                continue

            if link in existing_links:
                continue

            valid_links.append(link)
            existing_links.add(link)

        for link in valid_links:
            self._add_link_list_item(link)

        if valid_links:
            self.save_links()

        self.update_links_buttons_state()

        if invalid_lines:
            sample = "\n".join(invalid_lines[:3])
            extra = ""
            if len(invalid_lines) > 3:
                extra = f"\n...and {len(invalid_lines) - 3} more."

            QMessageBox.warning(
                self,
                "Invalid links detected",
                (
                    f"Some lines from {source_name} do not match the expected Apple Music link format "
                    f"and were skipped:\n\n{sample}{extra}"
                ),
            )

    def _is_valid_apple_music_link(self, link):
        return bool(self.APPLE_MUSIC_LINK_PATTERN.match(link))

    def _add_link_list_item(self, link):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, link)
        item.setSizeHint(QSize(0, 32))
        self.link_list.addItem(item)

        widget = LinkListItemWidget(link, self.copy_link_icon)
        widget.copy_requested.connect(self.copy_full_link)
        widget.row_clicked.connect(lambda item=item: self._toggle_link_item_selection(item))
        widget.set_selected(False)
        self.link_list.setItemWidget(item, widget)

    def copy_full_link(self, link):
        QApplication.clipboard().setText(link)

    def _get_link_list_item_link(self, item):
        if item is None:
            return ""

        return item.data(Qt.UserRole) or item.text() or ""

    def _toggle_link_item_selection(self, item):
        if item is None:
            return

        if item.isSelected():
            self.link_list.clearSelection()
            self.link_list.setCurrentRow(-1)
            return

        self.link_list.setCurrentItem(item)
        item.setSelected(True)

    def _clear_link_selection(self):
        if self.link_list.currentItem() is None and not self.link_list.selectedItems():
            return

        self.link_list.clearSelection()
        self.link_list.setCurrentRow(-1)

    def _is_widget_inside_link_list(self, widget):
        if widget is None or not isinstance(widget, QWidget):
            return False

        return widget is self.link_list or self.link_list.isAncestorOf(widget)

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.MouseButtonPress
            and self.link_list.count() > 0
        ):
            target_widget = None
            if hasattr(event, "globalPosition"):
                target_widget = QApplication.widgetAt(event.globalPosition().toPoint())

            if not self._is_widget_inside_link_list(target_widget):
                QTimer.singleShot(0, self._clear_link_selection)

        return super().eventFilter(watched, event)

    def _sync_link_item_selection_state(self):
        for index in range(self.link_list.count()):
            item = self.link_list.item(index)
            widget = self.link_list.itemWidget(item)
            if widget is not None:
                widget.set_selected(item.isSelected())

    def refresh_setup_buttons(self):
        emulator_running = self.emulator.is_emulator_running()
        emulator_booted = self.emulator.is_boot_completed()

        if self.emulator_start_in_progress and emulator_booted:
            self.emulator_start_in_progress = False
            self._hide_loading_overlay("emulator_boot")

        self._set_setup_button_enabled(self.emulator_button, not emulator_running)
        self._set_setup_button_enabled(self.frida_button, emulator_booted)

        self.update_start_button_state(emulator_running=emulator_running)

    def _set_setup_button_enabled(self, button, enabled):
        button.setEnabled(enabled)
        if hasattr(button, "step_label"):
            button.step_label.setEnabled(enabled)
        if hasattr(button, "text_label"):
            button.text_label.setEnabled(enabled)

    def is_required_setup_ready(self, emulator_running=None):
        if emulator_running is None:
            emulator_running = self.emulator.is_emulator_running()

        return emulator_running and self.frida.is_agent_running()

    def update_start_button_state(self, emulator_running=None):
        setup_ready = self.is_required_setup_ready(emulator_running=emulator_running)
        downloads_in_progress = bool(
            self.active_tasks or self.pending_downloads or self.preparation_in_progress
        )
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

        self._reset_download_results()
        self.downloader_config = read_downloader_config(get_amd_config_file())
        self.successful_downloads = []
        links = [
            self._get_link_list_item_link(self.link_list.item(i))
            for i in range(self.link_list.count())
        ]
        links = [link for link in links if link]
        self._begin_download_preparation(links)

    def _begin_download_preparation(self, links):
        self.preparation_in_progress = True
        self.update_start_button_state()

        self.preparation_thread = QThread(self)
        self.preparation_worker = DownloadPreparationWorker(
            links,
            self.download_destination,
            self.download_registry,
            self.downloader_config,
        )
        self.preparation_worker.moveToThread(self.preparation_thread)
        self.preparation_thread.started.connect(self.preparation_worker.run)
        self.preparation_worker.finished.connect(self._on_download_preparation_finished)
        self.preparation_worker.failed.connect(self._on_download_preparation_failed)
        self.preparation_worker.finished.connect(self.preparation_thread.quit)
        self.preparation_worker.failed.connect(self.preparation_thread.quit)
        self.preparation_thread.finished.connect(self._cleanup_preparation_worker)

        self._show_loading_overlay(
            "download_preparation",
            "Preparing Downloads",
            "Building the download queue. This can take a moment...",
        )
        self.preparation_thread.start()

    def _on_download_preparation_finished(self, pending_downloads, already_downloaded_count, updated_registry):
        self._hide_loading_overlay("download_preparation")
        self.preparation_in_progress = False
        self.download_registry = updated_registry
        self._save_download_registry()
        self.pending_downloads = list(pending_downloads)

        if not self.pending_downloads:
            if self.link_list.count() > 0 and already_downloaded_count == self.link_list.count():
                QMessageBox.information(
                    self,
                    "Nothing to download",
                    "All currently added links have already been downloaded.",
                )
            self.update_start_button_state()
            return

        self.update_start_button_state()
        self._start_next_downloads()

    def _on_download_preparation_failed(self, error_message):
        self._hide_loading_overlay("download_preparation")
        self.preparation_in_progress = False
        self.update_start_button_state()
        QMessageBox.warning(
            self,
            "Preparation failed",
            error_message or "The download queue could not be prepared.",
        )

    def _cleanup_preparation_worker(self):
        if self.preparation_worker is not None:
            self.preparation_worker.deleteLater()
            self.preparation_worker = None

        if self.preparation_thread is not None:
            self.preparation_thread.deleteLater()
            self.preparation_thread = None

    def _start_next_downloads(self):
        while (
            len(self.active_tasks) < self.max_simultaneous_downloads
            and self.pending_downloads
        ):
            download_item = self.pending_downloads.pop(0)
            link = download_item["link"]
            title = download_item["title"]

            widget = DownloadWidget(title)
            widget.set_status("active")
            self.active_download_layout.addWidget(widget)

            task = DownloadTask(link, widget.log_signal, on_finished=None)
            task.metadata = download_item.get("metadata")
            task.on_finished = (
                lambda success, current_task=task:
                self.download_finished_signal.emit(current_task, success)
            )

            self.task_widgets[task] = widget
            self.active_tasks.append(task)
            self._refresh_download_tab_labels()
            task.start()

    def _on_task_finished(self, task, success):
        if task in self.active_tasks:
            self.active_tasks.remove(task)

        widget = self.task_widgets.pop(task, None)

        if widget:
            self._move_widget_between_layouts(widget, self.active_download_layout)
            widget.set_details_expanded(False)

            if success:
                widget.set_status("success")
                self.success_download_layout.addWidget(widget)
                self.successful_downloads.append(
                    {
                        "link": task.link,
                        "metadata": getattr(task, "metadata", None),
                    }
                )
            else:
                error_message = self._build_task_error_message(task)
                widget.set_status("error", error_message)
                self.error_download_layout.addWidget(widget)
                self.failed_downloads.append(
                    {
                        "link": task.link,
                        "metadata": getattr(task, "metadata", None),
                        "reason": getattr(task, "failure_reason", None),
                    }
                )

            self._refresh_download_tab_labels()

        self._start_next_downloads()

        if not self.active_tasks and not self.pending_downloads:
            self._move_completed_downloads()
            self._record_completed_downloads()
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

    def _record_completed_downloads(self):
        if not self.successful_downloads:
            return

        registry_changed = False

        for download in self.successful_downloads:
            relative_path = self._find_existing_download_relative_path(
                download["link"],
                download.get("metadata"),
                allow_computed_without_registry=True,
            )
            if relative_path is None:
                continue

            if self._upsert_download_registry_entry(
                download["link"],
                download.get("metadata"),
                relative_path,
            ):
                registry_changed = True

        if registry_changed:
            self._save_download_registry()

        self.successful_downloads.clear()

    def _is_already_downloaded(self, link, metadata):
        was_downloaded = is_already_downloaded(
            self.download_destination,
            self.download_registry,
            self.downloader_config,
            link,
            metadata,
        )
        if was_downloaded:
            self._save_download_registry()
        return was_downloaded

    def _find_existing_download_relative_path(
        self,
        link,
        metadata,
        allow_computed_without_registry=False,
    ):
        if not self.download_destination:
            return None

        return find_existing_download_relative_path(
            self.download_destination,
            self.download_registry,
            self.downloader_config,
            link,
            metadata,
            allow_computed_without_registry=allow_computed_without_registry,
        )

    def _find_fuzzy_matching_relative_path(self, destination_root, relative_path):
        return find_fuzzy_matching_relative_path(destination_root, relative_path)

    def _find_matching_child_dir(self, parent_dir, expected_name):
        return find_matching_child_dir(parent_dir, expected_name)

    def _upsert_download_registry_entry(self, link, metadata, relative_path):
        return upsert_download_registry_entry(
            self.download_registry,
            link,
            metadata,
            relative_path,
        )

    def _save_download_registry(self):
        save_download_registry(self.download_registry_file, self.download_registry)

    def _reset_download_results(self):
        if self.preparation_worker is not None:
            self.preparation_worker.cancel()

        if self.preparation_thread is not None:
            self.preparation_thread.quit()

        self._hide_loading_overlay("download_preparation")
        self.preparation_in_progress = False
        self._cancel_all_tasks()
        self._clear_download_widgets()
        self.successful_downloads.clear()
        self.failed_downloads.clear()
        self.download_tabs.setCurrentIndex(0)

    def _move_widget_between_layouts(self, widget, source_layout):
        source_layout.removeWidget(widget)

    def _build_task_error_message(self, task):
        if getattr(task, "failure_reason", None) == "max_retries_reached":
            return "Max retries reached"

        if getattr(task, "result_status", None) == "cancelled":
            return "Cancelled"

        return "Download failed"

    def start_emulator(self):
        self.emulator.start(no_window=self.emulator_hidden_switch.isChecked())
        if self.emulator.is_emulator_running() and not self.emulator.is_boot_completed():
            self.emulator_start_in_progress = True
            self._show_loading_overlay(
                "emulator_boot",
                "Starting Emulator",
                "Waiting for the Android emulator to finish booting...",
            )
        self.refresh_setup_buttons()

    def prepare_frida(self):
        if not self.emulator.is_boot_completed() or self.frida_preparation_in_progress:
            return

        self.frida_preparation_in_progress = True
        self._show_loading_overlay(
            "frida_preparation",
            "Preparing Frida",
            "Starting frida-server and waiting for the Apple Music agent to connect...",
        )
        thread = threading.Thread(target=self._prepare_frida_worker, daemon=True)
        thread.start()

    def _prepare_frida_worker(self):
        try:
            self.frida.stop_frida()
            self.frida.enable_root()
            self.frida.disable_selinux()
            self.frida.start_frida_server()
            self.frida.forward_port()

            pid = self.frida.get_apple_music_pid()
            if not pid:
                self.frida_preparation_finished.emit(
                    False,
                    "Apple Music process not found. Open the app in the emulator and try again.",
                )
                return

            self.frida.attach_agent(pid)
            if not self.frida.is_agent_running():
                self.frida_preparation_finished.emit(
                    False,
                    "Frida agent could not attach to Apple Music.",
                )
                return

            self.frida_preparation_finished.emit(True, "")
        except Exception as exc:
            self.frida_preparation_finished.emit(False, str(exc))

    def _on_frida_preparation_finished(self, success, error_message):
        self.frida_preparation_in_progress = False
        self._hide_loading_overlay("frida_preparation")
        self.refresh_setup_buttons()

        if not success:
            QMessageBox.warning(
                self,
                "Frida setup failed",
                error_message or "Frida could not be prepared.",
            )

    def _cancel_all_tasks(self):
        self.pending_downloads.clear()

        for task in list(self.active_tasks):
            task.cancel()

        self.active_tasks.clear()
        self.task_widgets.clear()

    def _clear_download_widgets(self):
        for layout in (
            self.active_download_layout,
            self.success_download_layout,
            self.error_download_layout,
        ):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        self._refresh_download_tab_labels()

    def clear_downloads(self):
        """Cancela descargas, limpia widgets y borra subcarpetas go-build."""
        self._cancel_all_tasks()
        self._clear_download_widgets()
        self.successful_downloads.clear()
        self.failed_downloads.clear()
        self.download_tabs.setCurrentIndex(0)
        self.update_start_button_state()
        clean_go_build_subfolders()

    def closeEvent(self, event):
        if self.preparation_worker is not None:
            self.preparation_worker.cancel()

        if self.preparation_thread is not None:
            self.preparation_thread.quit()
            self.preparation_thread.wait(2000)

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
