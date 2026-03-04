"""
windows/furniture_shop_window.py - 가구 상점(배치 창과 동일한 UI 구성)

- PlacementPanel과 같은 구조:
  상단 타이틀 / 카테고리 버튼 row / 리스트(ThumbRow) / 하단 버튼
- ThumbRow의 버튼은:
  - 소지중이면 "소지중"
  - 아니면 "구매"
- 구매 시:
  state.money 차감
  state.owned_bg[cat]에 추가
  on_purchased 콜백 호출
"""

from typing import Dict, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QLabel, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QVBoxLayout, QWidget
)

from config import (
    BG_CATEGORIES, CAT_BTN_H, CAT_BTN_MIN_W,
    PLACEMENT_PANEL_W, PLACEMENT_PANEL_H, ROW_HEIGHT, THUMB_SIZE,
)
from utils.json_utils import get_catalog, resolve_bg_path
from ui.thumb_row import ThumbRow


class FurnitureShopWindow(QWidget):
    def __init__(self, state, app_icon: Optional[QIcon] = None, on_purchased=None):
        super().__init__()
        self.state = state
        self.on_purchased = on_purchased

        self.setWindowTitle("가구상점")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if app_icon:
            self.setWindowIcon(app_icon)

        # ✅ 배치 창과 동일 크기/스타일을 쓰고 싶다면 그대로 재사용
        self.setFixedSize(PLACEMENT_PANEL_W, PLACEMENT_PANEL_H)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        wrap = QWidget(self)
        wrap.setObjectName("Wrap")
        wrap.setStyleSheet("""
            QWidget#Wrap {
                background: rgba(255,255,255,220);
                border: 1px solid rgba(0,0,0,70);
                border-radius: 16px;
            }
        """)

        self.title = QLabel("🛒 가구상점", wrap)
        self.title.setStyleSheet("font-size: 16px; font-weight: 900;")

        self.money_label = QLabel("", wrap)
        self.money_label.setStyleSheet("font-size: 13px; font-weight: 900;")

        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(self.money_label, 0, Qt.AlignRight)

        self.cat_buttons: Dict[str, QPushButton] = {}
        self.list_area = QListWidget(wrap)
        self.list_area.setSpacing(8)
        self.list_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        reload_btn = QPushButton("🔄 목록 새로고침", wrap)
        reload_btn.setCursor(Qt.PointingHandCursor)
        reload_btn.setMinimumHeight(34)
        reload_btn.clicked.connect(self.open_category_refresh)

        close_btn = QPushButton("닫기", wrap)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setMinimumHeight(36)
        close_btn.clicked.connect(self.close)

        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)
        outer.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(6)
        for cat in BG_CATEGORIES:
            b = QPushButton(cat, wrap)
            b.setMinimumHeight(CAT_BTN_H)
            b.setMinimumWidth(CAT_BTN_MIN_W)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=cat: self.open_category(c))
            self.cat_buttons[cat] = b
            row.addWidget(b)
        outer.addLayout(row)

        outer.addWidget(self.list_area, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(reload_btn, 1)
        bottom.addWidget(close_btn, 0)
        outer.addLayout(bottom)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(wrap)

        self.current_cat = "wallpaper"
        self._refresh_money()
        self.open_category(self.current_cat)

    def _refresh_money(self):
        self.money_label.setText(f"💰 {int(getattr(self.state, 'money', 0))}원")

    def _notify(self):
        if callable(self.on_purchased):
            self.on_purchased()

    def open_category_refresh(self):
        self.open_category(self.current_cat)

    def _selected_style(self, cat: str, btn: QPushButton):
        if self.current_cat == cat:
            btn.setStyleSheet("""
                QPushButton {
                    padding: 6px 8px; border-radius: 12px;
                    border: 1px solid rgba(0,0,0,55);
                    background: rgba(220,240,255,245); font-weight: 900;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    padding: 6px 8px; border-radius: 12px;
                    border: 1px solid rgba(0,0,0,40);
                    background: rgba(255,255,255,245); font-weight: 900;
                }
            """)

    def _load_thumb(self, file_rel: str) -> Optional[QPixmap]:
        if not file_rel:
            return None
        p = resolve_bg_path(file_rel)
        if not p.exists():
            return None
        pm = QPixmap(str(p))
        return None if pm.isNull() else pm

    def _is_owned(self, cat: str, item_id: str) -> bool:
        owned = self.state.owned_bg.get(cat, set())
        if isinstance(owned, (list, tuple)):
            return item_id in owned
        return item_id in owned

    def _ensure_owned_set(self, cat: str):
        cur = self.state.owned_bg.get(cat)
        if cur is None:
            self.state.owned_bg[cat] = set()
            return
        if isinstance(cur, set):
            return
        # list/tuple 등 들어오면 set으로 정리
        self.state.owned_bg[cat] = set(cur)

    def _purchase(self, cat: str, item_id: str, price: int):
        if self._is_owned(cat, item_id):
            return
        money = int(getattr(self.state, "money", 0))
        if money < price:
            # 여기서 토스트/메시지 띄우고 싶으면 QMessageBox 추가해도 됨
            return

        self.state.money = money - int(price)
        self._ensure_owned_set(cat)
        self.state.owned_bg[cat].add(item_id)

        self._refresh_money()
        self._notify()
        self.open_category(cat)

    def open_category(self, cat: str):
        self.current_cat = cat
        self._refresh_money()

        for c, b in self.cat_buttons.items():
            self._selected_style(c, b)

        self.list_area.clear()

        catalog = get_catalog()
        items = catalog.get(cat, [])

        # 가독성: id 기준 정렬
        def sort_key(it):
            return str(it.get("id", ""))

        for it in sorted(items, key=sort_key):
            iid = str(it.get("id", "")).strip()
            if not iid:
                continue

            name = it.get("name", iid)
            file_rel = it.get("file", "")
            price = int(it.get("price", 0) or 0)

            owned = self._is_owned(cat, iid)
            thumb_pm = self._load_thumb(file_rel)

            btn_text = "소지중" if owned else "구매"
            price_text = "" if price <= 0 else f"{price}원"

            def make_onclick(_cat=cat, _iid=iid, _price=price, _owned=owned):
                def _cb():
                    if _owned:
                        return
                    self._purchase(_cat, _iid, _price)
                return _cb

            w = ThumbRow(
                title=str(name),
                subtitle=str(iid),
                pix=thumb_pm,
                button_text=btn_text,
                on_click=make_onclick(),
                selected=owned,              # 소지중이면 선택 스타일처럼 강조
                price_text=price_text,
                thumb_size=THUMB_SIZE,
                row_height=ROW_HEIGHT,
            )

            li = QListWidgetItem()
            li.setSizeHint(QSize(self.list_area.viewport().width() - 18, ROW_HEIGHT))
            self.list_area.addItem(li)
            self.list_area.setItemWidget(li, w)