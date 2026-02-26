"""
windows/shop_window.py - 상점 창
"""
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from config import ITEMS_JSON_PATH, SHOP_JSON_PATH
from state import PetState
from utils.helpers import load_json_file
from utils.json_utils import item_name, item_rarity


class ShopWindow(QWidget):
    def __init__(
        self,
        state: PetState,
        app_icon: Optional[QIcon] = None,
        shop_json_path: Path = SHOP_JSON_PATH,
        items_json_path: Path = ITEMS_JSON_PATH,
    ):
        super().__init__()
        self.state = state
        self.shop_json_path = shop_json_path
        self.items_json_path = items_json_path

        self.setWindowTitle("상점")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if app_icon:
            self.setWindowIcon(app_icon)

        self.shop_data = {}
        self.items_db = {}

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.money_label = QLabel("")
        self.money_label.setObjectName("MoneyLabel")
        top.addWidget(self.money_label)
        top.addStretch(1)

        hint = QLabel("상점에 들어올 때마다 자동으로 새로고침돼.")
        hint.setObjectName("HintLabel")
        top.addWidget(hint)
        layout.addLayout(top)

        self.category_list = QListWidget()
        self.category_list.setObjectName("ShopCategoryList")
        self.category_list.itemSelectionChanged.connect(self._on_category_changed)
        layout.addWidget(self.category_list)

        self.item_list = QListWidget()
        self.item_list.setObjectName("ShopItemList")
        layout.addWidget(self.item_list)

        btn_row = QHBoxLayout()
        self.buy_btn = QPushButton("구매")
        self.buy_btn.setObjectName("PrimaryButton")
        self.buy_btn.clicked.connect(self.buy_selected)
        btn_row.addStretch(1)
        btn_row.addWidget(self.buy_btn)
        layout.addLayout(btn_row)

        self.status = QLabel("")
        self.status.setObjectName("HintLabel")
        layout.addWidget(self.status)

        self.refresh_data()

    def showEvent(self, e):
        try:
            self.refresh_data()
        except Exception:
            pass
        super().showEvent(e)

    def refresh_data(self):
        self.shop_data = load_json_file(self.shop_json_path, fallback={"categories": [], "items": []})
        self.items_db = load_json_file(self.items_json_path, fallback={"items": []})

        self.category_list.clear()
        for cat in self.shop_data.get("categories", []):
            it = QListWidgetItem(cat.get("name", cat.get("id", "카테고리")))
            it.setData(Qt.UserRole, cat.get("id"))
            self.category_list.addItem(it)

        if self.category_list.count() > 0 and not self.category_list.currentItem():
            self.category_list.setCurrentRow(0)

        self._sync_money()

    def _sync_money(self):
        self.money_label.setText(f"소지금 {int(self.state.money)}")

    def _on_category_changed(self):
        self.item_list.clear()
        self.status.setText("")
        cat_id = None
        cur = self.category_list.currentItem()
        if cur:
            cat_id = cur.data(Qt.UserRole)

        items = []
        for it in self.shop_data.get("items", []):
            if it.get("category") == cat_id:
                items.append(it)

        for it in items:
            item_id = it.get("id")
            price = int(it.get("price", 0))
            name = item_name(self.items_db, item_id)
            rarity = item_rarity(self.items_db, item_id)
            label = f"{name}  ({price}원)  [{rarity}]"
            li = QListWidgetItem(label)
            li.setData(Qt.UserRole, it)
            self.item_list.addItem(li)

    def buy_selected(self):
        cur = self.item_list.currentItem()
        if not cur:
            self.status.setText("구매할 아이템을 선택해줘.")
            return

        data = cur.data(Qt.UserRole) or {}
        item_id = data.get("id")
        price = int(data.get("price", 0))
        qty = int(data.get("qty", 1))

        if self.state.money < price:
            self.status.setText("돈이 부족해…")
            return

        self.state.money -= price
        self.state.inventory[item_id] = int(self.state.inventory.get(item_id, 0)) + max(1, qty)
        self.status.setText(f"구매 완료! {item_name(self.items_db, item_id)} x{max(1, qty)}")
        self._sync_money()
