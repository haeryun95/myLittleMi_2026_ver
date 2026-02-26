"""
ui/thumb_row.py - ThumbRow 위젯 (썸네일 + 텍스트 + 버튼 행)
"""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ThumbRow(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str,
        pix: Optional[QPixmap],
        button_text: str,
        on_click,
        selected: bool = False,
        price_text: str = "",
        thumb_size: int = 84,
        row_height: int = 98,
        parent=None,
    ):
        super().__init__(parent)
        self.setFixedHeight(row_height)

        wrap = QFrame(self)
        wrap.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,235);
                border: 1px solid rgba(0,0,0,35);
                border-radius: 14px;
            }
        """)

        thumb = QLabel(wrap)
        thumb.setFixedSize(thumb_size, thumb_size)
        thumb.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,10);
                border: 1px solid rgba(0,0,0,30);
                border-radius: 12px;
            }
        """)
        if pix and not pix.isNull():
            thumb.setPixmap(
                pix.scaled(thumb_size - 8, thumb_size - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            thumb.setAlignment(Qt.AlignCenter)
        else:
            thumb.setText("없음")
            thumb.setAlignment(Qt.AlignCenter)

        title_lb = QLabel(title, wrap)
        title_lb.setStyleSheet("font-weight: 900; font-size: 14px;")
        title_lb.setWordWrap(True)

        sub_lb = QLabel(subtitle, wrap)
        sub_lb.setStyleSheet("color: rgba(0,0,0,160); font-size: 12px;")
        sub_lb.setWordWrap(True)

        price_lb = QLabel(price_text, wrap)
        price_lb.setStyleSheet("color: rgba(0,0,0,170); font-weight: 700; font-size: 12px;")

        btn = QPushButton(wrap)
        btn.setText(("✅ " if selected else "") + button_text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(34)
        btn.setStyleSheet("""
            QPushButton {
                text-align: center;
                padding: 8px 10px;
                border-radius: 12px;
                border: 1px solid rgba(0,0,0,40);
                background: rgba(255,255,255,245);
                font-weight: 900;
            }
            QPushButton:hover { background: rgba(255,255,255,255); }
        """)
        btn.clicked.connect(on_click)

        mid = QVBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(2)
        mid.addWidget(title_lb, 0)
        mid.addWidget(sub_lb, 0)
        mid.addWidget(price_lb, 0)
        mid.addStretch(1)

        row = QHBoxLayout(wrap)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)
        row.addWidget(thumb, 0, Qt.AlignVCenter)
        row.addLayout(mid, 1)
        row.addWidget(btn, 0, Qt.AlignVCenter)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(wrap)
