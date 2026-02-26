"""
windows/name_window.py - 펫 이름 변경 창
"""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from state import PetState


class NameWindow(QWidget):
    def __init__(self, state: PetState, app_icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state
        self.setWindowTitle("이름 변경")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if app_icon:
            self.setWindowIcon(app_icon)

        title = QLabel("💮 펫 이름 변경 💮")
        title.setObjectName("TitleLabel")

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("펫의 이름을 바꾸기")
        self.edit.setFixedHeight(30)
        self.edit.setText(self.state.pet_name)

        save_btn = QPushButton("저장")
        save_btn.clicked.connect(self.save)

        row = QHBoxLayout()
        row.addWidget(self.edit, 1)
        row.addWidget(save_btn, 0)

        hint = QLabel("최대 12자 권장")
        hint.setObjectName("HintLabel")

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addLayout(row)
        layout.addWidget(hint)
        self.setLayout(layout)

    def save(self):
        name = self.edit.text().strip() or "라이미"
        self.state.pet_name = name[:12]
        self.close()
