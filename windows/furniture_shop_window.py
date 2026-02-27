"""
windows/furniture_shop_window.py - 가구/배경 구매 상점
- furniture.json 기반
- 구매 시 state.owned_bg[cat]에 소유 등록
"""
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from state import PetState
from utils.json_utils import get_catalog


class FurnitureShopWindow(QWidget):
    def __init__(self, state: PetState, app_icon: Optional[QIcon] = None, on_purchased: Optional[Callable[[], None]] = None):
        super().__init__()
        self.state = state
        self.on_purchased = on_purchased

        self.setWindowTitle("가구 상점")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if app_icon:
            self.setWindowIcon(app_icon)

        self.catalog: Dict[str, List[dict]] = {}

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.money_label = QLabel("")
        self.money_label.setObjectName("MoneyLabel")
        top.addWidget(self.money_label)
        top.addStretch(1)

        self.hint = QLabel("furniture.json 기반으로 표시돼. (없으면 폴더 스캔 폴백)")
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

        self.reload()

    def showEvent(self, e):
        self.reload()
        super().showEvent(e)

    def reload(self):
        self.catalog = get_catalog()
        self._sync_money()

        self.category_list.clear()
        for cat in self.catalog.keys():
            it = QListWidgetItem(cat)
            it.setData(Qt.UserRole, cat)
            self.category_list.addItem(it)

        if self.category_list.count() > 0:
            self.category_list.setCurrentRow(0)
        else:
            self.status.setText("카탈로그가 비었어. background 폴더/ furniture.json 확인해줘.")

    def _sync_money(self):
        self.money_label.setText(f"소지금 {int(self.state.money)}")

    def _on_category_changed(self):
        self.item_list.clear()
        self.status.setText("")
        cur = self.category_list.currentItem()
        cat = cur.data(Qt.UserRole) if cur else None
        if not cat:
            return

        items = self.catalog.get(cat, [])
        owned = self.state.owned_bg.get(cat, set())

        for it in items:
            iid = it.get("id")
            name = it.get("name", iid)
            price = int(it.get("price", 0))
            is_owned = iid in owned
            tag = "소유중" if is_owned else f"{price}원"
            li = QListWidgetItem(f"{name}  [{tag}]")
            li.setData(Qt.UserRole, it)
            self.item_list.addItem(li)

        if not items:
            self.status.setText("이 카테고리에 표시할 항목이 없어.")

    def buy_selected(self):
        cur = self.item_list.currentItem()
        if not cur:
            self.status.setText("구매할 항목을 선택해줘.")
            return

        data = cur.data(Qt.UserRole) or {}
        iid = data.get("id")
        name = data.get("name", iid)
        price = int(data.get("price", 0))
        cat_item = self.category_list.currentItem()
        cat = cat_item.data(Qt.UserRole) if cat_item else None

        if not cat or not iid:
            self.status.setText("데이터가 이상해. furniture.json을 확인해줘.")
            return

        owned = self.state.owned_bg.setdefault(cat, set())
        if iid in owned:
            self.status.setText("이미 소유 중이야.")
            return

        if self.state.money < price:
            self.status.setText("돈이 부족해…")
            return

        self.state.money -= price
        owned.add(iid)
        self.status.setText(f"구매 완료! {name}")
        self._sync_money()

        if self.on_purchased:
            try:
                self.on_purchased()
            except Exception:
                pass

        # 리스트 갱신
        self._on_category_changed()