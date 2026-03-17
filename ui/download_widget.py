from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QTextEdit, QProgressBar, QSizePolicy
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

        self.title = QLabel(link)
        self.title.setWordWrap(True)
        layout.addWidget(self.title)

        # progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setLayout(layout)

        self.progress_active = False

        self.log_signal.connect(self.append_log)

        self.setStyleSheet("""
        #downloadCard {
            background-color: #2b2b2b;
            border: 1px solid #3c3c3c;
            border-radius: 8px;
            padding: 10px;
        }
        """)

    def append_log(self, text):

        # -------------------------
        # PROGRESS UPDATE
        # -------------------------
        if text.startswith("[PROGRESS]"):

            text = text.replace("[PROGRESS] ", "")

            # extraer porcentaje
            match = re.search(r'(\d+)%', text)
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

        # -------------------------
        # NORMAL LOG
        # -------------------------
        self.progress_active = False
        self.log.append(text)