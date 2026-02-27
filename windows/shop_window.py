"""
windows/shop_window.py - 소모품 상점 창
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

        self.setWindowTitle("소모품 상점")
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

        self.hint = QLabel("")
        self.hint.setObjectName("HintLabel")
        top.addWidget(self.hint)
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
        self.refresh_data()
        super().showEvent(e)

    def refresh_data(self):
        self.shop_data = load_json_file(self.shop_json_path, fallback={"categories": [], "items": []}) or {"categories": [], "items": []}
        self.items_db = load_json_file(self.items_json_path, fallback={"items": []}) or {"items": []}

        self._sync_money()

        # hint message
        if not self.shop_json_path.exists():
            self.hint.setText(f"⚠ shop.json 없음: {self.shop_json_path}")
        elif not self.items_json_path.exists():
            self.hint.setText(f"⚠ items.json 없음: {self.items_json_path}")
        else:
            self.hint.setText("상점은 열릴 때마다 자동 새로고침돼.")

        self.category_list.clear()
        cats = self.shop_data.get("categories", [])
        if not isinstance(cats, list):
            cats = []

        for cat in cats:
            it = QListWidgetItem(cat.get("name", cat.get("id", "카테고리")))
            it.setData(Qt.UserRole, cat.get("id"))
            self.category_list.addItem(it)

        if self.category_list.count() > 0:
            self.category_list.setCurrentRow(0)
        else:
            self.item_list.clear()
            self.status.setText("표시할 카테고리가 없어. shop.json의 categories를 확인해줘.")

    def _sync_money(self):
        self.money_label.setText(f"소지금 {int(self.state.money)}")

    def _on_category_changed(self):
        self.item_list.clear()
        self.status.setText("")

        cur = self.category_list.currentItem()
        cat_id = cur.data(Qt.UserRole) if cur else None

        items = self.shop_data.get("items", [])
        if not isinstance(items, list):
            items = []

        filtered = [it for it in items if it.get("category") == cat_id]
        if not filtered:
            self.status.setText("이 카테고리에 등록된 상품이 없어. shop.json의 items를 확인해줘.")
            return

        for it in filtered:
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