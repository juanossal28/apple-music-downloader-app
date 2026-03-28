from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QProgressBar,
    QSizePolicy,
    QToolButton,
    QWidget
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QTextCursor
import re


class DownloadWidget(QFrame):

    log_signal = Signal(str)

    def __init__(self, link):
        super().__init__()

        self.setObjectName("downloadCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.title = QLabel(link)
        self.title.setObjectName("downloadTitle")
        self.title.setWordWrap(True)
        self.title.setMaximumHeight(52)
        layout.addWidget(self.title)

        self.status_label = QLabel("Active")
        self.status_label.setObjectName("downloadStatus")
        self.status_label.setProperty("status", "active")
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("Waiting (%p%)")
        layout.addWidget(self.progress)

        self.log_toggle = QToolButton()
        self.log_toggle.setObjectName("logToggle")
        self.log_toggle.setText("Details")
        self.log_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.log_toggle.setArrowType(Qt.RightArrow)
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(False)
        self.log_toggle.toggled.connect(self._toggle_log)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.addWidget(self.log_toggle)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        self.log_container = QWidget()
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(0, 0, 0, 0)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.log.setMaximumHeight(110)
        log_layout.addWidget(self.log)

        self.log_container.setLayout(log_layout)
        layout.addWidget(self.log_container)

        self.setLayout(layout)

        self.progress_active = False

        self.collapsed_height = self.sizeHint().height()
        self._toggle_log(False)
        self.collapsed_height = self.sizeHint().height()
        self.setMinimumHeight(self.collapsed_height)
        self.setMaximumHeight(self.collapsed_height)

        self.log_signal.connect(self.append_log)

        self.setStyleSheet("""
        #downloadCard {
            background-color: #232629;
            border: 1px solid #2f3439;
            border-radius: 10px;
        }

        #downloadTitle {
            color: #f3f3f3;
            font-size: 9pt;
            font-weight: 600;
        }

        #downloadStatus {
            font-size: 8pt;
            font-weight: 600;
        }

        #downloadStatus[status="active"] {
            color: #8ab4f8;
        }

        #downloadStatus[status="success"] {
            color: #7bd88f;
        }

        #downloadStatus[status="error"] {
            color: #ff8a80;
        }

        #downloadStatus[status="cancelled"] {
            color: #f6c177;
        }

        QProgressBar {
            border: 1px solid #3a3f45;
            border-radius: 6px;
            text-align: center;
            background: #1d2024;
            color: #dfe6ee;
            height: 16px;
        }

        QProgressBar::chunk {
            border-radius: 5px;
            background-color: #4f9ef8;
        }

        #logToggle {
            border: none;
            color: #9ca3af;
            font-size: 8pt;
            padding: 0;
        }

        QTextEdit {
            background-color: #1d2024;
            border: 1px solid #343a40;
            border-radius: 6px;
            color: #cfd5de;
            font-family: Consolas, "Courier New", monospace;
            font-size: 8pt;
            padding: 10px 8px;
        }
        """)
        self.set_status("active")

    def _toggle_log(self, expanded):
        collapsed_height = getattr(self, "collapsed_height", self.sizeHint().height())
        self.collapsed_height = collapsed_height

        self.log_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.log_container.setVisible(expanded)

        if expanded:
            self.setMaximumHeight(16777215)
        else:
            self.setMaximumHeight(self.collapsed_height)

        self.setMinimumHeight(self.collapsed_height)
        self.updateGeometry()

    def append_log(self, text):

        if text.startswith("[PROGRESS]"):

            text = text.replace("[PROGRESS] ", "")

            match = re.search(r"(\d+)%", text)
            if match:
                percent = int(match.group(1))
                self.progress.setValue(percent)

                progress_label = text[:match.start()].strip().rstrip(".").strip()
                if progress_label:
                    self.progress.setFormat(f"{progress_label} (%p%)")

            cursor = self.log.textCursor()
            cursor.movePosition(QTextCursor.End)

            if self.progress_active:
                cursor.movePosition(QTextCursor.StartOfLine)
                cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            else:
                cursor.insertText("\n")

            cursor.insertText(text)

            self.log.setTextCursor(cursor)
            self.log.ensureCursorVisible()

            self.progress_active = True
            return

        self.progress_active = False
        self.log.append(text)

    def set_status(self, status, message=None):
        status_text_map = {
            "active": "Active",
            "success": "Successful",
            "error": "Error",
            "cancelled": "Cancelled",
        }
        label_text = status_text_map.get(status, status.title())
        if message:
            label_text = f"{label_text}: {message}"

        self.status_label.setText(label_text)
        self.status_label.setProperty("status", status)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

        if status == "success":
            self.progress.setValue(100)
            self.progress.setFormat("Completed (%p%)")
        elif status == "error":
            self.progress.setFormat("Failed (%p%)")
        elif status == "cancelled":
            self.progress.setFormat("Cancelled (%p%)")
        else:
            self.progress.setFormat("Waiting (%p%)")

    def set_details_expanded(self, expanded):
        self.log_toggle.setChecked(expanded)
