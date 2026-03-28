from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class SpinnerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._advance)
        self.setFixedSize(56, 56)

    def start(self):
        self._timer.start()
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _advance(self):
        self._angle = (self._angle + 1) % 12
        self.update()

    def paintEvent(self, event: QPaintEvent):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(self.width() / 2, self.height() / 2)

        base_color = QColor("#79b8ff")
        for index in range(12):
            painter.save()
            painter.rotate(index * 30.0)
            alpha = 35 + (((index - self._angle) % 12) * 18)
            color = QColor(base_color)
            color.setAlpha(min(alpha, 255))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(18, -4, 10, 10)
            painter.restore()


class LoadingDialog(QWidget):
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setAlignment(Qt.AlignCenter)

        self.panel = QFrame(self)
        self.panel.setObjectName("loadingPanel")
        self.panel.setFixedWidth(320)

        panel_layout = QVBoxLayout()
        panel_layout.setContentsMargins(26, 24, 26, 24)
        panel_layout.setSpacing(14)
        panel_layout.setAlignment(Qt.AlignCenter)

        self.spinner = SpinnerWidget()
        panel_layout.addWidget(self.spinner, alignment=Qt.AlignCenter)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("loadingTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        panel_layout.addWidget(self.title_label)

        self.message_label = QLabel(message)
        self.message_label.setObjectName("loadingMessage")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        panel_layout.addWidget(self.message_label)

        self.panel.setLayout(panel_layout)
        root_layout.addWidget(self.panel, alignment=Qt.AlignCenter)
        self.setLayout(root_layout)

        self.setStyleSheet("""
        QWidget {
            background: transparent;
        }

        #loadingPanel {
            background-color: rgba(20, 25, 32, 208);
            border: 1px solid rgba(152, 187, 255, 48);
            border-radius: 18px;
        }

        #loadingTitle {
            color: #f5f7fb;
            font-size: 12pt;
            font-weight: 700;
            background: transparent;
        }

        #loadingMessage {
            color: rgba(228, 234, 245, 0.88);
            font-size: 9pt;
            line-height: 1.4em;
            background: transparent;
        }
        """)
        self.hide()

    def set_content(self, title, message):
        self.setWindowTitle(title)
        self.title_label.setText(title)
        self.message_label.setText(message)
        self._sync_to_parent()

    def showEvent(self, event):
        self._sync_to_parent()
        self.raise_()
        self.spinner.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.spinner.stop()
        super().hideEvent(event)

    def paintEvent(self, event: QPaintEvent):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor(8, 12, 18, 150))
        gradient.setColorAt(0.55, QColor(16, 22, 31, 185))
        gradient.setColorAt(1.0, QColor(6, 9, 14, 160))
        painter.fillRect(self.rect(), gradient)

    def eventFilter(self, watched, event):
        if watched is self.parent() and event.type() in {
            QEvent.Move,
            QEvent.Resize,
            QEvent.Show,
        }:
            self._sync_to_parent()

        return super().eventFilter(watched, event)

    def _sync_to_parent(self):
        parent = self.parentWidget()
        if parent is None:
            return

        self.setGeometry(parent.rect())
        self.raise_()
