"""
windows/furniture_shop_window.py - 가구상점

요구사항 반영:
- 배치 창과 동일한 스타일/레이아웃 느낌
- 테마 버튼 이미지 시도 적용(없으면 기존 스타일 유지)
- i18n (state.lang 기반)
"""

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

try:
    from config import ASSET_DIR  # type: ignore
except Exception:
    ASSET_DIR = Path("asset")

from utils.json_utils import get_catalog
from ui.thumb_row import ThumbRow


def _guess_lang_from_state(state) -> str:
    for attr in ("lang", "language", "locale", "selected_lang"):
        v = getattr(state, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return "ko"


def _load_lang_dict(lang_code: str) -> Dict:
    code = (lang_code or "ko").strip().lower()
    p = ASSET_DIR / "lang" / f"{code}.json"
    if not p.exists():
        p = ASSET_DIR / "lang" / "ko.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _t(lang: Dict, path: str, fallback: str = ""):
    cur = lang
    for k in path.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return fallback
    return cur if isinstance(cur, str) else fallback


def _resolve_ui_asset(state, filename: str) -> Optional[str]:
    theme = getattr(state, "theme", None) or getattr(state, "selected_theme", None) or "default"
    theme = str(theme).strip() if theme else "default"
    cands = [
        ASSET_DIR / "ui" / theme / filename,
        ASSET_DIR / "ui" / "default" / filename,
        ASSET_DIR / "ui" / filename,
    ]
    for p in cands:
        try:
            if p.exists():
                return str(p.as_posix())
        except Exception:
            pass
    return None


def _apply_themed_button(btn: QPushButton, state, base_name: str):
    normal = _resolve_ui_asset(state, f"{base_name}.png")
    if not normal:
        return
    hover = _resolve_ui_asset(state, f"{base_name}_hover.png") or normal
    pressed = _resolve_ui_asset(state, f"{base_name}_pressed.png") or normal

    btn.setStyleSheet(f"""
        QPushButton {{
            border: none;
            background: transparent;
            border-image: url({normal}) 10 10 10 10 stretch stretch;
            padding: 6px 12px;
            font-weight: 900;
        }}
        QPushButton:hover {{
            border-image: url({hover}) 10 10 10 10 stretch stretch;
        }}
        QPushButton:pressed {{
            border-image: url({pressed}) 10 10 10 10 stretch stretch;
        }}
    """)


def _apply_panel_style(w: QWidget):
    # ✅ 배치/가구상점 공통 룩
    w.setStyleSheet("""
        QWidget#FurnitureShopWindow {
            background: rgba(255, 255, 255, 190);
            border: 1px solid rgba(0, 0, 0, 70);
            border-radius: 12px;
        }
        QLabel {
            color: rgba(0,0,0,200);
            font-weight: 900;
        }
        QListWidget {
            background: rgba(255,255,255,140);
            border: 1px solid rgba(0,0,0,55);
            border-radius: 10px;
            padding: 6px;
        }
    """)


class FurnitureShopWindow(QWidget):
    def __init__(
        self,
        state,
        app_icon: Optional[QIcon] = None,
        on_purchased: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("FurnitureShopWindow")

        self.state = state
        self.on_purchased = on_purchased
        self._lang = _load_lang_dict(_guess_lang_from_state(state))

        self.setWindowTitle(_t(self._lang, "ui.furniture_shop", "가구상점"))
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if app_icon:
            self.setWindowIcon(app_icon)

        self.setFixedSize(270, 320)
        _apply_panel_style(self)

        title = QLabel(_t(self._lang, "ui.furniture_shop", "가구상점"))
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.list = QListWidget()
        self.list.setSpacing(8)
        self.list.setIconSize(QSize(64, 64))

        self.close_btn = QPushButton(_t(self._lang, "ui.close", "닫기"))
        self.close_btn.clicked.connect(self.close)

        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,190);
                border: 1px solid rgba(0,0,0,60);
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 900;
                min-height: 28px;
            }
            QPushButton:hover { background: rgba(255,255,255,220); }
        """)
        _apply_themed_button(self.close_btn, self.state, "button_90x36")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.close_btn)

        self._populate()

    def _populate(self):
        self.list.clear()
        catalog = get_catalog()

        # ✅ "상점"이니 구매 가능한 카테고리만 (프로젝트 정책에 맞춰 조정 가능)
        for cat in ["wallpaper", "house", "wheel", "deco", "bridge", "flower"]:
            items: List[Dict] = catalog.get(cat, [])
            if not items:
                continue

            header_item = QListWidgetItem()
            header = QLabel(f"• {cat}")
            header.setStyleSheet("font-weight: 900; padding: 6px 2px;")
            header_item.setSizeHint(QSize(100, 26))
            self.list.addItem(header_item)
            self.list.setItemWidget(header_item, header)

            for it in items:
                iid = it.get("id")
                name = it.get("name", iid or "")
                price = int(it.get("price", 0) or 0)
                file_rel = it.get("file", "")

                if not iid:
                    continue

                owned = False
                try:
                    owned_set = self.state.owned_bg.get(cat, set())
                    if isinstance(owned_set, (list, tuple)):
                        owned = iid in owned_set
                    else:
                        owned = iid in owned_set
                except Exception:
                    owned = False

                selected = False
                try:
                    selected = (self.state.selected_bg.get(cat) == iid)
                except Exception:
                    selected = False

                # ✅ ThumbRow는 "선택" 버튼이 기본이라,
                #    여기서는 on_click을 "구매"로 사용(버튼 텍스트는 ThumbRow 구현에 따라 그대로일 수 있음)
                #    -> 만약 ThumbRow 버튼 텍스트를 바꿔야 하면, ThumbRow에 action_label 파라미터 추가로 확장 가능.
                row = ThumbRow(
                    category=cat,
                    item_id=iid,
                    name=str(name),
                    price=price,
                    file_rel=str(file_rel),
                    owned=owned,
                    selected=selected,
                    on_click=self._on_buy,
                    state=self.state,
                )

                li = QListWidgetItem()
                li.setSizeHint(row.sizeHint())
                self.list.addItem(li)
                self.list.setItemWidget(li, row)

    def _on_buy(self, cat: str, item_id: str):
        # ✅ 이미 소유면 아무것도 안 함(선택은 배치에서)
        try:
            owned_set = self.state.owned_bg.get(cat, set())
            already = item_id in owned_set if not isinstance(owned_set, (list, tuple)) else (item_id in owned_set)
            if already:
                return
        except Exception:
            pass

        # 가격 찾기
        catalog = get_catalog()
        price = 0
        for it in catalog.get(cat, []):
            if it.get("id") == item_id:
                price = int(it.get("price", 0) or 0)
                break

        # 돈 체크
        money = int(getattr(self.state, "money", 0) or 0)
        if money < price:
            # 너무 과한 UI 변경은 피하고, 최소 반응만
            return

        # 구매 처리
        try:
            self.state.money = money - price
        except Exception:
            pass

        try:
            owned = self.state.owned_bg.get(cat, set())
            if isinstance(owned, list):
                owned.append(item_id)
                self.state.owned_bg[cat] = owned
            elif isinstance(owned, tuple):
                self.state.owned_bg[cat] = set(list(owned) + [item_id])
            elif isinstance(owned, set):
                owned.add(item_id)
                self.state.owned_bg[cat] = owned
            else:
                # unknown type -> set로 교정
                s = set(owned) if owned else set()
                s.add(item_id)
                self.state.owned_bg[cat] = s
        except Exception:
            try:
                self.state.owned_bg[cat] = {item_id}
            except Exception:
                pass

        try:
            if self.on_purchased:
                self.on_purchased()
        except Exception:
            pass

        self._populate()