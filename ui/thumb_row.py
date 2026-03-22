"""
ui/thumb_row.py
게임 스타일 카드 UI
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import BG_DIR


class ThumbRow(QWidget):

    def __init__(
        self,
        category: str,
        item_id: str,
        name: str,
        price: int,
        file_rel: str,
        owned: bool,
        selected: bool,
        on_click,
        state,
        parent=None,
    ):
        super().__init__(parent)

        self.category = category
        self.item_id = item_id
        self.on_click = on_click

        self.setFixedHeight(104)

        # -------------------------
        # 카드 프레임
        # -------------------------

        card = QFrame(self)
        card.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,210);
                border: 1px solid rgba(0,0,0,50);
                border-radius: 16px;
            }
        """)

        # -------------------------
        # 썸네일
        # -------------------------

        thumb = QLabel()
        thumb.setFixedSize(76, 76)

        thumb.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,10);
                border: 1px solid rgba(0,0,0,30);
                border-radius: 12px;
            }
        """)

        pix = None

        try:
            path = (BG_DIR / file_rel).resolve()
            if path.exists():
                pix = QPixmap(str(path))
        except Exception:
            pass

        if pix and not pix.isNull():
            thumb.setPixmap(
                pix.scaled(
                    68,
                    68,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )
            thumb.setAlignment(Qt.AlignCenter)
        else:
            thumb.setText("?")
            thumb.setAlignment(Qt.AlignCenter)

        # -------------------------
        # 이름
        # -------------------------

        title = QLabel(name)
        title.setStyleSheet("""
            font-weight:900;
            font-size:15px;
        """)

        # -------------------------
        # 가격
        # -------------------------

        price_label = QLabel(f"💰 {price}")
        price_label.setStyleSheet("""
            background: rgba(255,240,190,220);
            border: 1px solid rgba(0,0,0,40);
            border-radius: 10px;
            padding: 2px 8px;
            font-size:12px;
            font-weight:800;
        """)

        # -------------------------
        # 상태 표시
        # -------------------------

        if owned:
            state_text = "보유"
            state_color = "rgba(200,255,200,200)"
        else:
            state_text = "미보유"
            state_color = "rgba(255,220,220,200)"

        state_label = QLabel(state_text)
        state_label.setStyleSheet(f"""
            background:{state_color};
            border-radius:8px;
            padding:2px 6px;
            font-size:11px;
            font-weight:700;
        """)

        # -------------------------
        # 버튼
        # -------------------------

        if owned:
            btn_text = "배치"
        else:
            btn_text = "구매"

        if selected:
            btn_text = "✅ 선택됨"

        btn = QPushButton(btn_text)

        btn.setMinimumHeight(36)

        btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,250);
                border: 1px solid rgba(0,0,0,50);
                border-radius: 12px;
                font-weight:900;
                padding:8px;
            }

            QPushButton:hover {
                background: rgba(255,255,255,255);
            }

            QPushButton:pressed {
                background: rgba(240,240,240,255);
            }
        """)

        btn.clicked.connect(self._clicked)

        # -------------------------
        # 텍스트 영역
        # -------------------------

        mid = QVBoxLayout()
        mid.setSpacing(4)
        mid.addWidget(title)

        row2 = QHBoxLayout()
        row2.addWidget(price_label)
        row2.addWidget(state_label)
        row2.addStretch()

        mid.addLayout(row2)
        mid.addStretch()

        # -------------------------
        # 카드 레이아웃
        # -------------------------

        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        layout.addWidget(thumb)
        layout.addLayout(mid, 1)
        layout.addWidget(btn)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(card)

    def _clicked(self):
        try:
            self.on_click(self.category, self.item_id)
        except Exception:
            pass