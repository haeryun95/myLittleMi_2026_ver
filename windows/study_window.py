"""
windows/study_window.py - 공부 창 (간식 + 소모품 상점)
"""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from state import PetState, clamp
from windows.shop_window import ShopWindow


class StudyWindow(QWidget):
    def __init__(self, state: PetState, shop_win: ShopWindow, app_icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state
        self.shop_win = shop_win

        self.setWindowTitle("공부")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if app_icon:
            self.setWindowIcon(app_icon)

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.money_label = QLabel("")
        self.money_label.setObjectName("MoneyLabel")
        top.addWidget(self.money_label)
        top.addStretch(1)
        layout.addLayout(top)

        self.study_btn = QPushButton("공부하기 (+흥미도/기분 소폭, 에너지 -6)")
        self.study_btn.setObjectName("PrimaryButton")
        self.study_btn.clicked.connect(self.do_study)
        layout.addWidget(self.study_btn)

        self.snack_btn = QPushButton("간식 주기 (300원)  배고픔 +10 / 재미 +3")
        self.snack_btn.clicked.connect(self.give_snack)
        layout.addWidget(self.snack_btn)

        self.shop_btn = QPushButton("소모품 상점 열기")
        self.shop_btn.setObjectName("MenuButton")
        self.shop_btn.clicked.connect(self.open_consumable_shop)
        layout.addWidget(self.shop_btn)

        self.result = QLabel("")
        self.result.setObjectName("HintLabel")
        layout.addWidget(self.result)

        self._sync_money()

    def showEvent(self, e):
        self._sync_money()
        super().showEvent(e)

    def _sync_money(self):
        self.money_label.setText(f"소지금 {int(self.state.money)}")

    def do_study(self):
        if self.state.energy < 6:
            self.result.setText("에너지가 부족해서 공부를 못 하겠어…")
            return
        self.state.energy = clamp(self.state.energy - 6, 0.0, self.state.max_energy)
        self.state.mood = clamp(self.state.mood + 1)
        self.state.fun = clamp(self.state.fun + 1)
        self.state.stats["interest"] = int(self.state.stats.get("interest", 0)) + 1
        self.result.setText("공부 완료! 머리가 조금 맑아졌어.")
        self._sync_money()

    def give_snack(self):
        cost = 300
        if self.state.money < cost:
            self.result.setText("돈이 부족해서 간식을 못 사…")
            return
        self.state.money -= cost
        self.state.hunger = clamp(self.state.hunger + 10)
        self.state.fun = clamp(self.state.fun + 3)
        self.state.mood = clamp(self.state.mood + 1)
        self.state.energy = clamp(self.state.energy + 1, 0.0, self.state.max_energy)
        self.result.setText("냠냠! 간식 맛있다 😋")
        self._sync_money()

    def open_consumable_shop(self):
        # shop은 열릴 때마다 자동 refresh(showEvent에서 처리)
        self.shop_win.show()
        self.shop_win.raise_()
        self.shop_win.activateWindow()