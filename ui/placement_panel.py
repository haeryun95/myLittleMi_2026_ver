"""
ui/placement_panel.py - 배경/가구 배치 패널
"""
from typing import Dict, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from config import (
    BG_CATEGORIES, CAT_BTN_H, CAT_BTN_MIN_W,
    PLACEMENT_PANEL_H, PLACEMENT_PANEL_W, ROW_HEIGHT, THUMB_SIZE,
)
from utils.json_utils import get_catalog, resolve_bg_path
from ui.thumb_row import ThumbRow


class PlacementPanel(QWidget):
    def __init__(self, state, on_changed=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.on_changed = on_changed

        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(PLACEMENT_PANEL_W, PLACEMENT_PANEL_H)

        wrap = QWidget(self)
        wrap.setObjectName("Wrap")
        wrap.setStyleSheet("""
            QWidget#Wrap {
                background: rgba(255,255,255,220);
                border: 1px solid rgba(0,0,0,70);
                border-radius: 16px;
            }
        """)

        title = QLabel("🏠 배치 변경", wrap)
        title.setStyleSheet("font-size: 16px; font-weight: 900;")

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
        outer.addWidget(title)

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
        self.open_category("wallpaper")

    def _notify(self):
        if callable(self.on_changed):
            self.on_changed()

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

    def open_category(self, cat: str):
        self.current_cat = cat
        for c, b in self.cat_buttons.items():
            self._selected_style(c, b)

        self.list_area.clear()

        if cat == "wallpaper":
            self._add_choice(cat, None, title="기본(default)", subtitle="아무 벽지도 선택하지 않음", file_rel="", price=0)
        else:
            self._add_choice(cat, None, title="없음(해제)", subtitle="이 카테고리 가구 숨기기", file_rel="", price=0)

        catalog = get_catalog()
        owned = self.state.owned_bg.get(cat, set())
        cat_items = {it["id"]: it for it in catalog.get(cat, [])}
        for iid in sorted(list(owned)):
            it = cat_items.get(iid, {"id": iid, "name": iid, "price": 0, "file": f"{cat}/{iid}.png"})
            self._add_choice(
                cat, it["id"],
                title=it.get("name", it["id"]),
                subtitle=it["id"],
                file_rel=it.get("file", ""),
                price=int(it.get("price", 0) or 0),
            )

    def _load_thumb(self, file_rel: str) -> Optional[QPixmap]:
        if not file_rel:
            return None
        p = resolve_bg_path(file_rel)
        if not p.exists():
            return None
        pm = QPixmap(str(p))
        return None if pm.isNull() else pm

    def _add_choice(self, cat: str, item_id: Optional[str], title: str, subtitle: str, file_rel: str, price: int):
        cur = self.state.selected_bg.get(cat)
        selected = (cur == item_id)
        thumb_pm = self._load_thumb(file_rel)
        price_text = "" if price <= 0 else f"{price}원"

        def on_click():
            self.state.selected_bg[cat] = item_id
            self._notify()
            self.open_category(cat)

        w = ThumbRow(
            title=title, subtitle=subtitle, pix=thumb_pm,
            button_text=("선택" if not selected else "선택됨"),
            on_click=on_click, selected=selected,
            price_text=price_text, thumb_size=THUMB_SIZE, row_height=ROW_HEIGHT,
        )

        it = QListWidgetItem()
        it.setSizeHint(QSize(self.list_area.viewport().width() - 18, ROW_HEIGHT))
        self.list_area.addItem(it)
        self.list_area.setItemWidget(it, w)
