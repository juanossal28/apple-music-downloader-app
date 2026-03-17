from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QProgressBar,
    QSizePolicy,
    QHBoxLayout,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
import re


class DownloadWidget(QFrame):

    log_signal = Signal(str)

    def __init__(self, link):
        super().__init__()
        self.setObjectName("downloadCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.title = QLabel(link)
        self.title.setObjectName("downloadTitle")
        self.title.setWordWrap(True)
        header_layout.addWidget(self.title, 1)

        self.status = QLabel("Queued")
        self.status.setObjectName("downloadStatus")
        header_layout.addWidget(self.status)

        layout.addLayout(header_layout)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setObjectName("downloadLog")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        layout.addWidget(self.log)

        self.setLayout(layout)

        self.progress_active = False

        self.log_signal.connect(self.append_log)

        self.setStyleSheet("""
        #downloadCard {
            background-color: #202225;
            border: 1px solid #3b3f46;
            border-radius: 10px;
        }
        QLabel#downloadTitle {
            font-size: 13px;
            font-weight: 600;
            color: #f1f1f1;
        }
        QLabel#downloadStatus {
            color: #9aa0a6;
            background-color: #2a2d31;
            border: 1px solid #3a3e44;
            border-radius: 6px;
            padding: 2px 8px;
        }
        QTextEdit#downloadLog {
            background-color: #181a1d;
            border: 1px solid #2f3338;
            border-radius: 6px;
            color: #d1d5db;
            font-family: Consolas, monospace;
            font-size: 11px;
        }
        QProgressBar {
            border: 1px solid #31363b;
            border-radius: 6px;
            background-color: #16181b;
            text-align: center;
            color: #ffffff;
            height: 14px;
        }
        QProgressBar::chunk {
            border-radius: 5px;
            background-color: #27ae60;
        }
        """)

    def append_log(self, text):

        if text.startswith("[PROGRESS]"):
            text = text.replace("[PROGRESS] ", "")
            self.status.setText("In progress")

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

        if "[CANCELLED]" in text:
            self.status.setText("Cancelled")
        elif "Download finished" in text:
            self.status.setText("Completed")
            self.progress.setValue(100)

        self.progress_active = False
        self.log.append(text)
