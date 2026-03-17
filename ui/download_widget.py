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
        self.setMinimumHeight(230)
        self.setMaximumHeight(230)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.title = QLabel(link)
        self.title.setObjectName("downloadTitle")
        self.title.setWordWrap(True)
        self.title.setMaximumHeight(52)
        layout.addWidget(self.title)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.log_toggle = QToolButton()
        self.log_toggle.setObjectName("logToggle")
        self.log_toggle.setText("Details")
        self.log_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.log_toggle.setArrowType(Qt.DownArrow)
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(True)
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

        self.log_signal.connect(self.append_log)

        self.setStyleSheet("""
        #downloadCard {
            background-color: #232629;
            border: 1px solid #2f3439;
            border-radius: 10px;
        }

        #downloadTitle {
            color: #f3f3f3;
            font-size: 12px;
            font-weight: 600;
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
            font-size: 11px;
            padding: 0;
        }

        QTextEdit {
            background-color: #1d2024;
            border: 1px solid #343a40;
            border-radius: 6px;
            color: #cfd5de;
            font-family: Consolas, "Courier New", monospace;
            font-size: 11px;
            padding: 4px;
        }
        """)

    def _toggle_log(self, expanded):
        self.log_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.log_container.setVisible(expanded)

    def append_log(self, text):

        if text.startswith("[PROGRESS]"):

            text = text.replace("[PROGRESS] ", "")

            match = re.search(r"(\d+)%", text)
            if match:
                percent = int(match.group(1))
                self.progress.setValue(percent)

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
