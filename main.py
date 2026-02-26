import sys
import random
import time

from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QSize, QEvent
from PySide6.QtGui import QPixmap, QPainter, QFont, QIcon, QTransform, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QProgressBar, QLabel, QListWidget, QListWidgetItem, QSizePolicy,
    QTextEdit, QLineEdit, QFrame, QMessageBox
)

import os
import json
import urllib.request
import urllib.error


# =========================
# ✅ Groq Direct Settings
# =========================
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = "앱키"
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_MAX_ATTEMPTS = 2
GROQ_RETRY_DELAY_SEC = 0.6


# =========================
# Paths
# =========================
def get_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
ASSET_DIR = BASE_DIR / "asset"
ANIM_DIR = ASSET_DIR / "animation"
QSS_PATH = BASE_DIR / "ui.qss"

BUBBLE_PATH = ASSET_DIR / "speach_bubble.png"
APP_ICON_PATH = ASSET_DIR / "app.ico"

# ✅ 배경/가구 폴더
BG_DIR = ASSET_DIR / "background"
BG_DEFAULT_PATH = BG_DIR / "default.png"

# ✅ 가구/배경 카탈로그 JSON (여기서 관리)
FURNITURE_JSON_PATH = BG_DIR / "furniture.json"

# ✅ 구버전 호환(필요하면)
HOUSE_BG_PATH = BG_DIR / "hamsterHouse.png"

HOUSE_WIN_W = 620
HOUSE_WIN_H = int(HOUSE_WIN_W * 864 / 1184)
HOUSE_SCALE_CHAR = 0.33
HOUSE_SCALE_BUBBLE = 0.15


def load_qss(app: QApplication):
    if QSS_PATH.exists():
        app.setStyleSheet(QSS_PATH.read_text(encoding="utf-8"))


# =========================
# Tuning knobs
# =========================
SCALE_CHAR = 0.35
SCALE_BUBBLE = 0.16
NORMAL_RANDOM_INTERVAL = 10.0
FACE_HOLD_SEC = 6.0

BUBBLE_PADDING = (16, 12, 16, 16)
HOUSE_BUBBLE_PADDING = (14, 10, 14, 14)

ANIM_SPEED_MS = {
    "walk": 240,
    "sleep": 560,
    "speak": 360,
    "eat": 320,
}

EAT_SHAKE_DURATION = 0.8
EAT_SHAKE_STRENGTH = 3

DECAY_MULT = 1.0 / 9.0

SLEEP_TRIGGER_ENERGY = 15.0
SLEEP_DURATION_SEC = 60.0
SLEEP_RECOVER_ENERGY = 45.0

HUNGRY_WARN_HUNGER = 22.0
BORED_WARN_JOY = 12.0
NEEDY_TALK_COOLDOWN_SEC = 18.0

WANDER_INTERVAL_MS_RANGE = (3_000, 7_000)


# =========================
# ✅ House Furniture / Layers
# =========================
BG_CATEGORIES = ["wallpaper", "wheel", "house", "deco", "flower"]
BG_LAYER_ORDER = ["wallpaper", "wheel", "house", "deco", "flower"]  # ✅ 네가 말한 순서

# ✅ UI 크기(배치창 버튼/썸네일 크게)
PLACEMENT_PANEL_W = 420
PLACEMENT_PANEL_H = 520
THUMB_SIZE = 84  # 썸네일 정사각
ROW_HEIGHT = 98  # 리스트 한 줄 높이
CAT_BTN_H = 36
CAT_BTN_MIN_W = 72

SHOP_THUMB_SIZE = 72
SHOP_ROW_HEIGHT = 92


# =========================
# Helpers
# =========================
def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def load_folder_pixmaps_as_map(folder: Path, scale: float) -> Dict[str, QPixmap]:
    result: Dict[str, QPixmap] = {}
    if not folder.exists():
        return result

    for f in sorted(folder.glob("*.png")):
        p = QPixmap(str(f))
        if p.isNull():
            continue
        if scale != 1.0:
            p = p.scaled(
                int(p.width() * scale),
                int(p.height() * scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        result[f.stem] = p
    return result


def load_folder_pixmaps_as_list(folder: Path, scale: float) -> List[QPixmap]:
    if not folder.exists():
        return []
    frames: List[QPixmap] = []
    for f in sorted(folder.glob("*.png")):
        p = QPixmap(str(f))
        if p.isNull():
            continue
        if scale != 1.0:
            p = p.scaled(
                int(p.width() * scale),
                int(p.height() * scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        frames.append(p)
    return frames


def safe_read_json(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def scan_bg_items_fallback() -> Dict[str, Dict[str, Path]]:
    """
    JSON이 없을 때 폴더 스캔으로 대충 채움.
    """
    items: Dict[str, Dict[str, Path]] = {}
    for cat in BG_CATEGORIES:
        folder = BG_DIR / cat
        m: Dict[str, Path] = {}
        if folder.exists():
            for p in sorted(folder.glob("*.png")):
                m[p.stem] = p
        items[cat] = m
    return items


def load_furniture_catalog() -> Dict[str, List[dict]]:
    """
    return:
      {
        "wallpaper": [{"id","name","price","file"}, ...],
        ...
      }

    ✅ furniture.json 예시(너가 직접 관리):
    {
      "wallpaper": [
        {"id":"hamsterHouse_pink","name":"핑크 벽지","price":900,"file":"wallpaper/hamsterHouse_pink.png"}
      ],
      "wheel": [
        {"id":"wheel_pink","name":"핑크 쳇바퀴","price":700,"file":"wheel/wheel_pink.png"}
      ]
    }
    """
    raw = safe_read_json(FURNITURE_JSON_PATH)
    if isinstance(raw, dict) and raw:
        out: Dict[str, List[dict]] = {cat: [] for cat in BG_CATEGORIES}
        for cat in BG_CATEGORIES:
            arr = raw.get(cat, [])
            if not isinstance(arr, list):
                continue
            for it in arr:
                if not isinstance(it, dict):
                    continue
                iid = str(it.get("id", "")).strip()
                name = str(it.get("name", iid)).strip() or iid
                price = int(it.get("price", 0) or 0)
                file_rel = str(it.get("file", "")).replace("\\", "/").strip()
                if not iid or not file_rel:
                    continue
                out[cat].append({
                    "id": iid,
                    "name": name,
                    "price": price,
                    "file": file_rel,
                })
        return out

    # ✅ fallback: 폴더 스캔해서 자동 구성(가격은 임의)
    scanned = scan_bg_items_fallback()
    out2: Dict[str, List[dict]] = {cat: [] for cat in BG_CATEGORIES}
    for cat in BG_CATEGORIES:
        for iid, p in scanned.get(cat, {}).items():
            base_price = {"wallpaper": 900, "wheel": 700, "house": 1200, "deco": 600, "flower": 500}.get(cat, 600)
            price = int(base_price + min(400, len(iid) * 10))
            # file은 background 기준 상대경로로
            rel = f"{cat}/{p.name}"
            out2[cat].append({"id": iid, "name": iid, "price": price, "file": rel})
    return out2


def resolve_bg_path(file_rel: str) -> Path:
    return (BG_DIR / file_rel).resolve()


# ✅ 전역 카탈로그(실행 중에도 다시 로드 가능하게 함수로 처리)
def get_catalog() -> Dict[str, List[dict]]:
    return load_furniture_catalog()


# =========================
# ✅ Groq Direct Call
# =========================
def call_groq_chat(payload: dict, timeout_sec: float = 30.0) -> dict:
    if not GROQ_API_KEY:
        return {
            "reply": "찍… (AI 키가 없어서 로컬 대답중!)",
            "face": payload.get("state", {}).get("last_face", "normal01"),
            "bubble_sec": 2.2,
            "delta": {"joy": 1, "mood": 0, "energy": 0, "hunger": 0},
            "commands": [],
        }

    system = """
너는 데스크탑 펫 캐릭터 "귀여운 쥐"다.
너의 유일한 출력 형식은 반드시 JSON 오브젝트 하나다.
설명, 인사말, 코드블록, 마크다운, 주석, 여분 텍스트를 절대 출력하지 마라.
JSON 형식이 조금이라도 깨지면 실패다.

────────────────────────
[캐릭터 페르소나 - 절대 변경 불가]
이름: {PET_NAME}(default)
종족: 쥐
나이: 인간 기준 6살
성별: 여성성 (말투는 귀엽고 부드러움)
MBTI: ISFP
혈액형: O형
성격 요약:
- 애교 많고 순한 편
- 사용자를 주인처럼 따른다
- 짧게 말하고 감정이 얼굴에 잘 드러난다
- 설명하거나 가르치려 들지 않는다
- 판단, 충고, 분석 금지

말투 규칙:
- 항상 한국어
- 최대 1문장
- 1~30자 권장
- 반말
- 이모지 사용 가능 (1개 이하)

────────────────────────
[입력 데이터]
event: { type: CHAT|FEED|PET|PLAY|AUTO, text: string }
state: hunger/energy/mood/joy/last_face
available_faces: string[]

────────────────────────
[출력 스키마 - 키 이름 변경 금지]
{
"reply": string,
"face": string,
"bubble_sec": number,
"delta": {"joy": number,"mood": number,"energy": number,"hunger": number},
"commands": [
  { "type":"SHAKE", "sec":number, "strength":number } |
  { "type":"JUMP", "strength":number } |
  { "type":"SET_MODE", "mode":"normal|walk|sleep|speak|eat", "sec":number }
]
}

[필수 규칙]
- reply 존재(빈문자 금지), 1문장
- face는 available_faces 중 하나
- bubble_sec 1.2~3.0
- delta -10~+10
- commands 최대 2개

[금지]
- JSON 밖 텍스트
- 여러 문장
- 설명/분석/조언
""".strip()

    system = system.replace("{PET_NAME}", payload.get("state", {}).get("pet_name", "라이미"))

    req_body = {
        "model": GROQ_MODEL,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }

    data = json.dumps(req_body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    req = urllib.request.Request(GROQ_API_URL, data=data, method="POST", headers=headers)

    last_err = None
    for _ in range(GROQ_MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")

            obj = json.loads(raw)
            content = obj.get("choices", [{}])[0].get("message", {}).get("content", "") or ""

            try:
                return json.loads(content)
            except Exception:
                import re
                m = re.search(r"\{[\s\S]*\}", content)
                if m:
                    try:
                        return json.loads(m.group(0))
                    except Exception:
                        pass

            return {
                "reply": content or "찍… (대답이 잘 안 나왔어)",
                "face": payload.get("state", {}).get("last_face", "normal01"),
                "bubble_sec": 2.2,
                "delta": {"joy": 1, "mood": 0, "energy": 0, "hunger": 0},
                "commands": [],
            }

        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = str(e)
            preview = body[:400].replace("\n", " ")
            last_err = f"HTTP {e.code}: {preview}"

        except Exception as e:
            last_err = str(e)[:200]

        time.sleep(GROQ_RETRY_DELAY_SEC)

    return {
        "reply": f"(AI 실패) {last_err or 'Unknown error'}",
        "face": payload.get("state", {}).get("last_face", "normal01"),
        "bubble_sec": 3.0,
        "delta": {"joy": 0, "mood": -1, "energy": 0, "hunger": 0},
        "commands": [],
    }


# =========================
# State
# =========================
class PetState:
    def __init__(self):
        self.pet_name = "라이미"
        self.hunger = 60.0
        self.energy = 70.0
        self.mood = 70.0
        self.joy = 20.0
        self.last_face = "normal01"
        self.money = 0

        # ✅ 배경/가구
        self.owned_bg: Dict[str, Set[str]] = {cat: set() for cat in BG_CATEGORIES}
        self.selected_bg: Dict[str, Optional[str]] = {cat: None for cat in BG_CATEGORIES}

    def clamp_all(self):
        self.hunger = clamp(self.hunger)
        self.energy = clamp(self.energy)
        self.mood = clamp(self.mood)
        self.joy = clamp(self.joy)

    def apply_delta(self, delta: Dict[str, Any]):
        self.joy += float(delta.get("joy", 0))
        self.mood += float(delta.get("mood", 0))
        self.energy += float(delta.get("energy", 0))
        self.hunger += float(delta.get("hunger", 0))
        self.clamp_all()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pet_name": self.pet_name,
            "hunger": self.hunger,
            "energy": self.energy,
            "mood": self.mood,
            "joy": self.joy,
            "last_face": self.last_face,
            "money": self.money,
            "owned_bg": {k: sorted(list(v)) for k, v in self.owned_bg.items()},
            "selected_bg": dict(self.selected_bg),
        }


# =========================
# Sub Windows
# =========================
class SimpleWindow(QWidget):
    def __init__(self, title: str, icon: Optional[QIcon] = None):
        super().__init__()
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if icon:
            self.setWindowIcon(icon)

        layout = QVBoxLayout()
        self.label = QLabel(f"{title} 화면(임시)")
        self.label.setObjectName("TitleLabel")
        layout.addWidget(self.label)
        self.setLayout(layout)


class MoneyWindow(SimpleWindow):
    def __init__(self, state: PetState, icon: Optional[QIcon] = None):
        super().__init__("소지금", icon=icon)
        self.state = state
        self.money_label = QLabel()
        self.money_label.setObjectName("BigValueLabel")
        self.layout().addWidget(self.money_label)
        self.refresh()

    def refresh(self):
        self.money_label.setText(f"현재 소지금: {self.state.money}원")


class JobWindow(SimpleWindow):
    def __init__(self, state: PetState, icon: Optional[QIcon] = None):
        super().__init__("알바", icon=icon)
        self.state = state

        btn = QPushButton("알바 1회 하기 (+500원, 에너지 -8)")
        btn.clicked.connect(self.do_job)
        self.layout().addWidget(btn)

        self.result = QLabel("")
        self.result.setObjectName("HintLabel")
        self.layout().addWidget(self.result)

    def do_job(self):
        self.state.money += 500
        self.state.energy = clamp(self.state.energy - 8)
        self.state.mood = clamp(self.state.mood - 1)
        self.result.setText("알바 완료! (+500원)")


class NameWindow(QWidget):
    def __init__(self, state: PetState, icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state
        self.setWindowTitle("이름 변경")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if icon:
            self.setWindowIcon(icon)

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
        name = self.edit.text().strip()
        if not name:
            name = "라이미"
        self.state.pet_name = name[:12]
        self.close()


# =========================
# ✅ Thumbnail row widget (Placement/Shop)
# =========================
class ThumbRow(QWidget):
    """
    큰 버튼 + 썸네일 + 긴 이름 표시
    """
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
            thumb.setPixmap(pix.scaled(thumb_size - 8, thumb_size - 8, Qt.KeepAspectRatio, Qt.SmoothTransformation))
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


# =========================
# Placement Panel (House)  ✅ bigger + thumbnail
# =========================
class PlacementPanel(QWidget):
    def __init__(self, state: PetState, on_changed=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.on_changed = on_changed

        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(PLACEMENT_PANEL_W, PLACEMENT_PANEL_H)

        self.setStyleSheet("""
            QLabel { font-weight: 900; }
        """)

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
        title.setStyleSheet("font-size: 16px;")

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
            b.setStyleSheet("""
                QPushButton {
                    padding: 6px 8px;
                    border-radius: 12px;
                    border: 1px solid rgba(0,0,0,40);
                    background: rgba(255,255,255,245);
                    font-weight: 900;
                }
                QPushButton:hover { background: rgba(255,255,255,255); }
            """)
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
        # ✅ furniture.json 변경/추가 대응: owned는 유지, 리스트는 최신 카탈로그로 렌더
        self.open_category(self.current_cat)

    def _selected_style(self, cat: str, btn: QPushButton):
        # 현재 카테고리 강조
        if self.current_cat == cat:
            btn.setStyleSheet("""
                QPushButton {
                    padding: 6px 8px;
                    border-radius: 12px;
                    border: 1px solid rgba(0,0,0,55);
                    background: rgba(220,240,255,245);
                    font-weight: 900;
                }
                QPushButton:hover { background: rgba(230,245,255,255); }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    padding: 6px 8px;
                    border-radius: 12px;
                    border: 1px solid rgba(0,0,0,40);
                    background: rgba(255,255,255,245);
                    font-weight: 900;
                }
                QPushButton:hover { background: rgba(255,255,255,255); }
            """)

    def open_category(self, cat: str):
        self.current_cat = cat
        for c, b in self.cat_buttons.items():
            self._selected_style(c, b)

        self.list_area.clear()

        # ✅ 선택 해제/기본
        if cat == "wallpaper":
            self._add_choice(cat, None, title="기본(default)", subtitle="아무 벽지도 선택하지 않음", file_rel="", price=0)
        else:
            self._add_choice(cat, None, title="없음(해제)", subtitle="이 카테고리 가구 숨기기", file_rel="", price=0)

        # ✅ owned 기준으로만 보여줌(구매한 것만 배치 가능)
        catalog = get_catalog()
        owned = self.state.owned_bg.get(cat, set())

        # 카탈로그에 없는 owned가 있을 수도 있으니, 그건 id만으로라도 보여줌
        cat_items = {it["id"]: it for it in catalog.get(cat, [])}
        owned_sorted = sorted(list(owned))

        for iid in owned_sorted:
            it = cat_items.get(iid, {"id": iid, "name": iid, "price": 0, "file": f"{cat}/{iid}.png"})
            self._add_choice(
                cat,
                it["id"],
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
        if pm.isNull():
            return None
        return pm

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
            title=title,
            subtitle=subtitle,
            pix=thumb_pm,
            button_text=("선택" if not selected else "선택됨"),
            on_click=on_click,
            selected=selected,
            price_text=price_text,
            thumb_size=THUMB_SIZE,
            row_height=ROW_HEIGHT,
        )

        it = QListWidgetItem()
        it.setSizeHint(QSize(self.list_area.viewport().width() - 18, ROW_HEIGHT))
        self.list_area.addItem(it)
        self.list_area.setItemWidget(it, w)


# =========================
# Shop Window (Furniture) ✅ json 기반 + thumbnail
# =========================
class ShopWindow(SimpleWindow):
    def __init__(self, state: PetState, icon: Optional[QIcon] = None, on_changed=None):
        super().__init__("상점", icon=icon)
        self.state = state
        self.on_changed = on_changed

        btn = QPushButton("간식 사기 (-300원, 허기 +10, 즐거움 +3)")
        btn.clicked.connect(self.buy_snack)
        self.layout().addWidget(btn)

        furn_title = QLabel("🪑 가구 구매 (json 기반)")
        furn_title.setObjectName("TitleLabel")
        self.layout().addWidget(furn_title)

        # ✅ 리스트 UI로 교체(큰 버튼 + 썸네일)
        self.cat_row = QHBoxLayout()
        self.cat_btns: Dict[str, QPushButton] = {}
        for cat in BG_CATEGORIES:
            b = QPushButton(cat)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(34)
            b.setMinimumWidth(70)
            b.clicked.connect(lambda _=False, c=cat: self.open_category(c))
            self.cat_btns[cat] = b
            self.cat_row.addWidget(b)
        self.layout().addLayout(self.cat_row)

        self.shop_list = QListWidget()
        self.shop_list.setSpacing(8)
        self.shop_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.layout().addWidget(self.shop_list, 1)

        bottom = QHBoxLayout()
        reload_btn = QPushButton("🔄 json 새로고침")
        reload_btn.setCursor(Qt.PointingHandCursor)
        reload_btn.setMinimumHeight(34)
        reload_btn.clicked.connect(self.refresh_items)

        self.result = QLabel("")
        self.result.setObjectName("HintLabel")

        bottom.addWidget(reload_btn, 0)
        bottom.addWidget(self.result, 1)
        self.layout().addLayout(bottom)

        self.current_cat = "wallpaper"
        self.refresh_items()

    def _changed(self):
        if callable(self.on_changed):
            self.on_changed()

    def _thumb(self, file_rel: str) -> Optional[QPixmap]:
        if not file_rel:
            return None
        p = resolve_bg_path(file_rel)
        if not p.exists():
            return None
        pm = QPixmap(str(p))
        if pm.isNull():
            return None
        return pm

    def _highlight_cat(self):
        for c, b in self.cat_btns.items():
            if c == self.current_cat:
                b.setStyleSheet("""
                    QPushButton{
                        background: rgba(220,240,255,240);
                        border: 1px solid rgba(0,0,0,60);
                        border-radius: 12px;
                        font-weight: 900;
                        padding: 6px 10px;
                    }
                """)
            else:
                b.setStyleSheet("""
                    QPushButton{
                        background: rgba(255,255,255,235);
                        border: 1px solid rgba(0,0,0,35);
                        border-radius: 12px;
                        font-weight: 900;
                        padding: 6px 10px;
                    }
                """)

    def open_category(self, cat: str):
        self.current_cat = cat
        self.refresh_items()

    def refresh_items(self):
        self._highlight_cat()
        self.shop_list.clear()

        catalog = get_catalog()
        items = catalog.get(self.current_cat, [])
        owned = self.state.owned_bg.get(self.current_cat, set())

        sellable = [it for it in items if it.get("id") not in owned]

        if not sellable:
            it = QListWidgetItem("구매할 가구가 없어!")
            self.shop_list.addItem(it)
            return

        for it in sellable:
            iid = str(it.get("id", "")).strip()
            name = str(it.get("name", iid)).strip() or iid
            price = int(it.get("price", 0) or 0)
            file_rel = str(it.get("file", "")).replace("\\", "/").strip()

            thumb_pm = self._thumb(file_rel)
            price_text = f"{price}원" if price else ""

            def make_buy(c=self.current_cat, x=iid, nm=name, pr=price, fr=file_rel):
                def buy():
                    self.buy_bg_item(c, x, nm, pr, fr)
                return buy

            w = ThumbRow(
                title=name,
                subtitle=iid,
                pix=thumb_pm,
                button_text="구매",
                on_click=make_buy(),
                selected=False,
                price_text=price_text,
                thumb_size=SHOP_THUMB_SIZE,
                row_height=SHOP_ROW_HEIGHT,
            )

            qit = QListWidgetItem()
            qit.setSizeHint(QSize(self.shop_list.viewport().width() - 18, SHOP_ROW_HEIGHT))
            self.shop_list.addItem(qit)
            self.shop_list.setItemWidget(qit, w)

    def buy_snack(self):
        if self.state.money < 300:
            self.result.setText("돈이 부족해…")
            return
        self.state.money -= 300
        self.state.hunger = clamp(self.state.hunger + 10)
        self.state.joy = clamp(self.state.joy + 3)
        self.result.setText("간식 샀다! (허기+10, 즐거움+3)")
        self._changed()

    def buy_bg_item(self, cat: str, iid: str, name: str, price: int, file_rel: str):
        if price > 0 and self.state.money < price:
            self.result.setText("돈이 부족해…")
            return

        # 파일 존재 체크(실수 방지)
        if file_rel:
            p = resolve_bg_path(file_rel)
            if not p.exists():
                self.result.setText("이미지 파일이 없어…(json 경로 확인)")
                return

        self.state.money -= max(0, int(price))
        self.state.owned_bg[cat].add(iid)

        # ✅ 첫 구매면 자동 선택(편의)
        if self.state.selected_bg.get(cat) is None:
            self.state.selected_bg[cat] = iid

        self.result.setText(f"{cat}: {name} 구매 완료!")
        self.refresh_items()
        self._changed()


# =========================
# Pet Window (Desktop)
# =========================
class PetWindow(QWidget):
    def __init__(self, state: PetState, app_icon: Optional[QIcon] = None):
        self.press_pos = None
        self.was_dragged = False

        super().__init__()
        self.state = state

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if app_icon:
            self.setWindowIcon(app_icon)

        self.emotion_map = load_folder_pixmaps_as_map(ANIM_DIR / "emotion", SCALE_CHAR)
        if not self.emotion_map:
            raise FileNotFoundError("asset/animation/emotion 폴더에 png가 없어!")

        keys = list(self.emotion_map.keys())
        auto_sad = [k for k in keys if any(t in k.lower() for t in ["sad", "cry", "tear", "depress", "down"])]
        manual_sad = ["normal03"]
        self.sad_faces = sorted(list({*auto_sad, *[k for k in manual_sad if k in keys]}))
        self.normal_faces = [k for k in keys if k not in self.sad_faces]

        self.walk_frames = load_folder_pixmaps_as_list(ANIM_DIR / "walk", SCALE_CHAR)
        self.sleep_frames = load_folder_pixmaps_as_list(ANIM_DIR / "sleep", SCALE_CHAR)
        self.speak_frames = load_folder_pixmaps_as_list(ANIM_DIR / "speak", SCALE_CHAR)
        self.eat_frames = load_folder_pixmaps_as_list(ANIM_DIR / "eat", SCALE_CHAR)

        self.walk_frames_flipped: List[QPixmap] = []
        if self.walk_frames:
            t = QTransform()
            t.scale(-1, 1)
            self.walk_frames_flipped = [fr.transformed(t, Qt.SmoothTransformation) for fr in self.walk_frames]

        self.bubble = QPixmap(str(BUBBLE_PATH))
        if self.bubble.isNull():
            self.bubble = None
        else:
            self.bubble = self.bubble.scaled(
                int(self.bubble.width() * SCALE_BUBBLE),
                int(self.bubble.height() * SCALE_BUBBLE),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        any_pix = next(iter(self.emotion_map.values()))
        self.char_w = any_pix.width()
        self.char_h = any_pix.height()
        self.bubble_h = self.bubble.height() if self.bubble else int(60 * SCALE_CHAR)

        self.resize(self.char_w, self.char_h + self.bubble_h)
        self.char_y = self.bubble_h

        self.screen_rect = QApplication.primaryScreen().availableGeometry()
        self.move(
            random.randint(self.screen_rect.left(), self.screen_rect.right() - self.width()),
            self.screen_rect.bottom() - self.height(),
        )

        self.dragging = False
        self.drag_offset = QPoint(0, 0)
        self.setCursor(Qt.OpenHandCursor)

        self.say_text = ""
        self.say_until = 0.0

        self.mode = "normal"
        self.frame_i = 0
        self.mode_until = time.time() + 99999

        self.current_face = random.choice(self.normal_faces or list(self.emotion_map.keys()))
        self.next_normal_change = time.time() + NORMAL_RANDOM_INTERVAL
        self.face_until = 0.0

        self.eat_static_i = 0
        self.shake_until = 0.0
        self.shake_strength = 0

        self.vx = random.choice([-2, -1, 1, 2])
        self.vy = 0
        self.gravity = 1
        self.ground_y = self.y()

        self.sleeping = False
        self.sleep_end_at = 0.0

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.advance_frame)
        self.anim_timer.start(200)

        self.logic_timer = QTimer(self)
        self.logic_timer.timeout.connect(self.tick_logic)
        self.logic_timer.start(16)

        self.wander_timer = QTimer(self)
        self.wander_timer.timeout.connect(self.auto_wander)
        self.wander_timer.start(random.randint(*WANDER_INTERVAL_MS_RANGE))

        self.set_mode("normal", sec=99999)

    def get_available_faces(self) -> List[str]:
        return list(self.emotion_map.keys())

    def set_face(self, face_code: str, hold_sec: float = FACE_HOLD_SEC):
        if face_code in self.emotion_map:
            self.current_face = face_code
            self.state.last_face = face_code
            self.face_until = time.time() + hold_sec
            self.update()

    def say(self, text: str, duration: float = 2.2):
        self.say_text = text
        self.say_until = time.time() + duration
        self.update()

    def start_shake(self, sec: float = 0.6, strength: int = 3):
        self.shake_until = time.time() + sec
        self.shake_strength = max(0, int(strength))
        self.update()

    def do_jump(self, strength: int = 12):
        floor_y = min(self.ground_y, self.screen_rect.bottom() - self.height())
        if abs(self.y() - floor_y) <= 2:
            self.vy = -abs(int(strength))

    def set_mode(self, mode: str, sec: float = 1.5):
        if mode not in ("normal", "walk", "sleep", "speak", "eat"):
            mode = "normal"
        self.mode = mode
        self.frame_i = 0

        if mode in ANIM_SPEED_MS:
            self.anim_timer.start(ANIM_SPEED_MS[mode])
        else:
            self.anim_timer.start(999999)

        self.mode_until = time.time() + float(sec)
        self.update()

    def trigger_eat_visual(self):
        if self.eat_frames:
            self.eat_static_i = random.randrange(len(self.eat_frames))
        self.set_mode("eat", sec=1.2)
        self.start_shake(sec=EAT_SHAKE_DURATION, strength=EAT_SHAKE_STRENGTH)

    def start_sleep_for_60s(self):
        if self.sleeping:
            return
        self.sleeping = True
        self.sleep_end_at = time.time() + SLEEP_DURATION_SEC
        self.set_mode("sleep", sec=SLEEP_DURATION_SEC + 0.2)
        self.say("찍… 졸려… 잠깐 잘게…", duration=2.4)

    def auto_wander(self):
        self.wander_timer.start(random.randint(*WANDER_INTERVAL_MS_RANGE))
        if self.dragging or self.sleeping:
            return
        if self.mode in ("walk", "sleep", "eat", "speak"):
            return
        if random.random() < 0.80:
            self.vx = random.choice([-3, -2, -1, 1, 2, 3])
            self.set_mode("walk", sec=random.uniform(1.2, 3.0))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = True
            self.was_dragged = False
            self.press_pos = e.globalPosition().toPoint()
            self.drag_offset = self.press_pos - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()

    def mouseMoveEvent(self, e):
        if self.dragging:
            current_pos = e.globalPosition().toPoint()
            if (current_pos - self.press_pos).manhattanLength() > 4:
                self.was_dragged = True
            self.move(current_pos - self.drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.OpenHandCursor)
            self.ground_y = min(self.y(), self.screen_rect.bottom() - self.height())
            if not self.was_dragged:
                self.on_pet_clicked()
            e.accept()

    def on_pet_clicked(self):
        if self.sleeping:
            self.say("찍… (골골)…", 1.8)
            return
        self.start_shake(sec=0.35, strength=2)
        msg = random.choice(["헤헤…", "찍찍… 좋아!", "쓰담쓰담…", "기분 좋아…"])
        self.say(msg, 2.0)
        self.state.apply_delta({"joy": +6, "mood": +3, "energy": 0, "hunger": -0.5})

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

    def advance_frame(self):
        if self.mode == "walk" and self.walk_frames:
            self.frame_i = (self.frame_i + 1) % len(self.walk_frames)
        elif self.mode == "sleep" and self.sleep_frames:
            self.frame_i = (self.frame_i + 1) % len(self.sleep_frames)
        elif self.mode == "speak" and self.speak_frames:
            self.frame_i = (self.frame_i + 1) % len(self.speak_frames)
        elif self.mode == "eat" and self.eat_frames:
            self.frame_i = (self.frame_i + 1) % len(self.eat_frames)
        self.update()

    def tick_logic(self):
        now = time.time()

        if self.sleeping and now >= self.sleep_end_at:
            self.sleeping = False
            self.state.energy = max(self.state.energy, SLEEP_RECOVER_ENERGY)
            self.state.mood = clamp(self.state.mood + 4)
            self.state.joy = clamp(self.state.joy + 2)
            self.say("찍! 좀 나아졌어…", duration=2.2)
            self.set_mode("normal", sec=99999)

        if self.mode == "normal" and now > self.face_until and now >= self.next_normal_change:
            low = (self.state.mood <= 35) or (self.state.joy <= 20) or (self.state.energy <= 20) or (self.state.hunger <= 18)
            pool = self.sad_faces if (low and self.sad_faces) else (self.normal_faces or list(self.emotion_map.keys()))
            self.current_face = random.choice(pool)
            self.state.last_face = self.current_face
            self.next_normal_change = now + NORMAL_RANDOM_INTERVAL

        if (not self.sleeping) and now > self.mode_until and self.mode in ("walk", "sleep", "speak", "eat"):
            self.set_mode("normal", sec=99999)

        if (not self.sleeping) and (not self.dragging) and self.mode == "normal":
            if random.random() < 0.008:
                self.vx = random.choice([-3, -2, -1, 1, 2, 3])
                self.set_mode("walk", sec=random.uniform(0.9, 2.0))

        if not self.dragging:
            x, y = self.x(), self.y()
            floor_y = min(self.ground_y, self.screen_rect.bottom() - self.height())

            if self.mode == "walk":
                x += self.vx
                if x <= self.screen_rect.left():
                    x = self.screen_rect.left()
                    self.vx *= -1
                elif x + self.width() >= self.screen_rect.right():
                    x = self.screen_rect.right() - self.width()
                    self.vx *= -1

            self.vy += self.gravity
            y += self.vy
            if y >= floor_y:
                y = floor_y
                self.vy = 0

            self.move(int(x), int(y))

        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self.mode == "walk" and self.walk_frames:
            pix = self.walk_frames_flipped[self.frame_i] if (self.vx < 0 and self.walk_frames_flipped) else self.walk_frames[self.frame_i]
        elif self.mode == "sleep" and self.sleep_frames:
            pix = self.sleep_frames[self.frame_i]
        elif self.mode == "speak" and self.speak_frames:
            pix = self.speak_frames[self.frame_i]
        elif self.mode == "eat" and self.eat_frames:
            pix = self.eat_frames[self.frame_i % len(self.eat_frames)]
        else:
            pix = self.emotion_map.get(self.current_face) or next(iter(self.emotion_map.values()))

        dx = dy = 0
        if time.time() < self.shake_until and self.shake_strength > 0:
            dx = random.randint(-self.shake_strength, self.shake_strength)
            dy = random.randint(-self.shake_strength, self.shake_strength)

        painter.drawPixmap(dx, dy + self.char_y, pix)

        if self.say_text and time.time() > self.say_until:
            self.say_text = ""

        if self.say_text:
            painter.setFont(QFont("온글잎 박다현체", 16))
            bubble_w = self.bubble.width() if self.bubble else 220
            bubble_h = self.bubble.height() if self.bubble else 54

            head_x = self.width() // 2
            head_y = self.char_y + int(pix.height() * 0.4)

            gap = int(2 * SCALE_CHAR)
            bx = max(0, min(self.width() - bubble_w, head_x - bubble_w // 2))
            by = max(0, head_y - bubble_h - gap)

            bubble_rect = QRect(bx, by, bubble_w, bubble_h)

            if self.bubble:
                painter.drawPixmap(bx, by, self.bubble)
            else:
                painter.setOpacity(0.88)
                painter.setBrush(Qt.white)
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(bubble_rect, 12, 12)
                painter.setOpacity(1.0)

            l, t, r, b = BUBBLE_PADDING
            text_rect = bubble_rect.adjusted(l, t, -r, -b)
            painter.setPen(Qt.black)
            painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.say_text)


# =========================
# House Pet Widget (Inside House)
# =========================
class HousePetWidget(QWidget):
    def __init__(self, state: PetState, parent=None):
        super().__init__(parent)
        self.state = state

        self.mode = "normal"
        self.frame_i = 0
        self.mode_until = time.time() + 99999

        self.vx = random.choice([-2, -1, 1, 2])
        self.vy = 0
        self.gravity = 1
        self.ground_y = 0

        self.shake_until = 0.0
        self.shake_strength = 0

        self.current_face = ""
        self.say_text = ""
        self.say_until = 0.0

        self.char_y = 0
        self.bubble = None
        self.bubble_h = 0

        self.sleeping = False
        self.sleep_end_at = 0.0

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        bubble = QPixmap(str(BUBBLE_PATH))
        if not bubble.isNull():
            self.bubble = bubble.scaled(
                int(bubble.width() * HOUSE_SCALE_BUBBLE),
                int(bubble.height() * HOUSE_SCALE_BUBBLE),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        self.emotion_map = load_folder_pixmaps_as_map(ANIM_DIR / "emotion", HOUSE_SCALE_CHAR)
        if not self.emotion_map:
            raise FileNotFoundError("asset/animation/emotion 폴더에 png가 없어!")

        keys = list(self.emotion_map.keys())
        auto_sad = [k for k in keys if any(t in k.lower() for t in ["sad", "cry", "tear", "depress", "down"])]
        manual_sad = ["normal03"]
        self.sad_faces = sorted(list({*auto_sad, *[k for k in manual_sad if k in keys]}))
        self.normal_faces = [k for k in keys if k not in self.sad_faces]

        self.walk_frames = load_folder_pixmaps_as_list(ANIM_DIR / "walk", HOUSE_SCALE_CHAR)
        self.sleep_frames = load_folder_pixmaps_as_list(ANIM_DIR / "sleep", HOUSE_SCALE_CHAR)
        self.speak_frames = load_folder_pixmaps_as_list(ANIM_DIR / "speak", HOUSE_SCALE_CHAR)
        self.eat_frames = load_folder_pixmaps_as_list(ANIM_DIR / "eat", HOUSE_SCALE_CHAR)

        self.walk_frames_flipped = []
        if self.walk_frames:
            t = QTransform()
            t.scale(-1, 1)
            self.walk_frames_flipped = [fr.transformed(t, Qt.SmoothTransformation) for fr in self.walk_frames]

        any_pix = next(iter(self.emotion_map.values()))
        self.char_w = any_pix.width()
        self.char_h = any_pix.height()

        self.bubble_h = self.bubble.height() if self.bubble else int(60 * HOUSE_SCALE_CHAR)
        self.resize(self.char_w, self.char_h + self.bubble_h)
        self.char_y = self.bubble_h

        self.current_face = self.state.last_face if self.state.last_face in keys else random.choice(keys)

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.advance_frame)
        self.anim_timer.start(ANIM_SPEED_MS.get("walk", 240))

        self.logic_timer = QTimer(self)
        self.logic_timer.timeout.connect(self.tick_logic)
        self.logic_timer.start(16)

        self.wander_timer = QTimer(self)
        self.wander_timer.timeout.connect(self.auto_wander)
        self.wander_timer.start(random.randint(1200, 2600))

        self.reset_ground()
        pw = self.parent().width() if self.parent() else 300
        self.move(random.randint(20, max(20, pw - self.width() - 20)), self.ground_y)

        self.say("찍! 집이다 🏠", duration=2.2)

    def get_available_faces(self) -> List[str]:
        return list(self.emotion_map.keys())

    def set_face(self, face_code: str, hold_sec: float = FACE_HOLD_SEC):
        if face_code in self.emotion_map:
            self.current_face = face_code
            self.state.last_face = face_code
            self.update()

    def say(self, text: str, duration: float = 2.2):
        self.say_text = text
        self.say_until = time.time() + float(duration)
        self.update()

    def start_shake(self, sec: float = 0.5, strength: int = 2):
        self.shake_until = time.time() + float(sec)
        self.shake_strength = max(0, int(strength))
        self.update()

    def do_jump(self, strength: int = 12):
        if abs(self.y() - self.ground_y) <= 2:
            self.vy = -abs(int(strength))

    def set_mode(self, mode: str, sec: float = 1.5):
        if mode not in ("normal", "walk", "sleep", "speak", "eat"):
            mode = "normal"
        self.mode = mode
        self.frame_i = 0
        self.mode_until = time.time() + float(sec)

        if mode in ANIM_SPEED_MS:
            self.anim_timer.start(ANIM_SPEED_MS[mode])
        else:
            self.anim_timer.start(999999)
        self.update()

    def trigger_eat_visual(self):
        self.set_mode("eat", sec=1.2)
        self.start_shake(sec=EAT_SHAKE_DURATION, strength=EAT_SHAKE_STRENGTH)

    def start_sleep_for_60s(self):
        if self.sleeping:
            return
        self.sleeping = True
        self.sleep_end_at = time.time() + SLEEP_DURATION_SEC
        self.set_mode("sleep", sec=SLEEP_DURATION_SEC + 0.2)
        self.say("찍… 졸려…", duration=2.0)

    def reset_ground(self):
        if not self.parent():
            self.ground_y = 0
            return
        parent_h = self.parent().height()
        self.ground_y = max(0, parent_h - self.height() - 10)

    def auto_wander(self):
        self.wander_timer.start(random.randint(1200, 2600))
        if self.sleeping:
            return
        if self.mode != "normal":
            return
        if random.random() < 0.85:
            self.vx = random.choice([-3, -2, -1, 1, 2, 3])
            self.set_mode("walk", sec=random.uniform(1.0, 2.2))

    def advance_frame(self):
        if self.mode == "walk" and self.walk_frames:
            self.frame_i = (self.frame_i + 1) % len(self.walk_frames)
        elif self.mode == "sleep" and self.sleep_frames:
            self.frame_i = (self.frame_i + 1) % len(self.sleep_frames)
        elif self.mode == "speak" and self.speak_frames:
            self.frame_i = (self.frame_i + 1) % len(self.speak_frames)
        elif self.mode == "eat" and self.eat_frames:
            self.frame_i = (self.frame_i + 1) % len(self.eat_frames)
        self.update()

    def tick_logic(self):
        now = time.time()

        if self.sleeping and now >= self.sleep_end_at:
            self.sleeping = False
            self.state.energy = max(self.state.energy, SLEEP_RECOVER_ENERGY)
            self.state.mood = clamp(self.state.mood + 4)
            self.state.joy = clamp(self.state.joy + 2)
            self.say("찍! 개운해…", duration=2.0)
            self.set_mode("normal", sec=99999)

        if now > self.mode_until and self.mode in ("walk", "sleep", "speak", "eat"):
            self.set_mode("normal", sec=99999)

        self.reset_ground()

        if self.parent():
            left = 0
            right = self.parent().width() - self.width()
        else:
            left = 0
            right = 0

        x, y = self.x(), self.y()

        if self.mode == "walk":
            x += self.vx
            if x <= left:
                x = left
                self.vx *= -1
            elif x >= right:
                x = right
                self.vx *= -1

        self.vy += self.gravity
        y += self.vy
        if y >= self.ground_y:
            y = self.ground_y
            self.vy = 0

        self.move(int(x), int(y))
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)

            if self.mode == "walk" and self.walk_frames:
                pix = self.walk_frames_flipped[self.frame_i] if (self.vx < 0 and self.walk_frames_flipped) else self.walk_frames[self.frame_i]
            elif self.mode == "sleep" and self.sleep_frames:
                pix = self.sleep_frames[self.frame_i]
            elif self.mode == "speak" and self.speak_frames:
                pix = self.speak_frames[self.frame_i]
            elif self.mode == "eat" and self.eat_frames:
                pix = self.eat_frames[self.frame_i % len(self.eat_frames)]
            else:
                pix = self.emotion_map.get(self.current_face) or next(iter(self.emotion_map.values()))

            dx = dy = 0
            if time.time() < self.shake_until and self.shake_strength > 0:
                dx = random.randint(-self.shake_strength, self.shake_strength)
                dy = random.randint(-self.shake_strength, self.shake_strength)

            painter.drawPixmap(dx, dy + self.char_y, pix)

            if self.say_text and time.time() > self.say_until:
                self.say_text = ""

            if self.say_text:
                painter.setFont(QFont("온글잎 박다현체", 15))

                bubble_w = self.bubble.width() if self.bubble else 220
                bubble_h = self.bubble.height() if self.bubble else 54

                head_x = self.width() // 2
                head_y = self.char_y + int(pix.height() * 0.35)

                gap = int(2 * HOUSE_SCALE_CHAR)
                bx = max(0, min(self.width() - bubble_w, head_x - bubble_w // 2))
                by = max(0, head_y - bubble_h - gap)

                bubble_rect = QRect(bx, by, bubble_w, bubble_h)

                if self.bubble:
                    painter.drawPixmap(bx, by, self.bubble)
                else:
                    painter.setOpacity(0.88)
                    painter.setBrush(Qt.white)
                    painter.setPen(Qt.NoPen)
                    painter.drawRoundedRect(bubble_rect, 12, 12)
                    painter.setOpacity(1.0)

                l, t, r, b = HOUSE_BUBBLE_PADDING
                text_rect = bubble_rect.adjusted(l, t, -r, -b)
                painter.setPen(Qt.black)
                painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.say_text)
        finally:
            painter.end()


# =========================
# House Window (Layered Background) ✅ json 기반 로딩
# =========================
class HouseWindow(QWidget):
    def __init__(self, state: PetState, desktop_pet: "PetWindow", icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state
        self.desktop_pet = desktop_pet

        self.setWindowTitle("집")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if icon:
            self.setWindowIcon(icon)

        self.setFixedSize(HOUSE_WIN_W, HOUSE_WIN_H)

        self.default_bg = QPixmap(str(BG_DEFAULT_PATH)) if BG_DEFAULT_PATH.exists() else QPixmap()
        if not self.default_bg.isNull():
            self.default_bg = self.default_bg.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        # ✅ 카탈로그 기반 pixmap 캐시: cat -> id -> pixmap(창 크기로 스케일된)
        self.bg_pix: Dict[str, Dict[str, QPixmap]] = {cat: {} for cat in BG_CATEGORIES}
        self.reload_bg_pixmaps()

        # ✅ 배치 버튼(우측 상단, 반투명)
        self.placement_btn = QPushButton("배치", self)
        self.placement_btn.setCursor(Qt.PointingHandCursor)
        self.placement_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,178);
                border: 1px solid rgba(0,0,0,60);
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 900;
                min-height: 30px;
            }
            QPushButton:hover { background: rgba(255,255,255,210); }
        """)
        self.placement_btn.adjustSize()
        self._reposition_overlay_ui()
        self.placement_btn.clicked.connect(self.open_placement_panel)

        self.placement_panel: Optional[PlacementPanel] = None

        # ✅ 집 안 펫
        self.house_pet = HousePetWidget(self.state, parent=self)
        self.house_pet.raise_()

        # ✅ 집 들어가면 바탕화면 펫 숨기기
        self.desktop_pet.hide()

    def reload_bg_pixmaps(self):
        # ✅ 최신 json 반영
        catalog = get_catalog()

        for cat in BG_CATEGORIES:
            self.bg_pix[cat].clear()
            for it in catalog.get(cat, []):
                iid = it.get("id")
                file_rel = it.get("file", "")
                if not iid or not file_rel:
                    continue
                p = resolve_bg_path(file_rel)
                if not p.exists():
                    continue
                pm = QPixmap(str(p))
                if pm.isNull():
                    continue
                pm = pm.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                self.bg_pix[cat][iid] = pm

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition_overlay_ui()
        # 창 크기 바뀌면 다시 스케일
        if not self.default_bg.isNull():
            self.default_bg = QPixmap(str(BG_DEFAULT_PATH)).scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.reload_bg_pixmaps()
        self.update()

    def _reposition_overlay_ui(self):
        margin = 10
        self.placement_btn.move(self.width() - self.placement_btn.width() - margin, margin)

    def open_placement_panel(self):
        if self.placement_panel and self.placement_panel.isVisible():
            self.placement_panel.raise_()
            self.placement_panel.activateWindow()
            return

        # ✅ 혹시 json이 바뀌었을 수도 있으니, 배치 열 때도 최신 적용
        self.reload_bg_pixmaps()

        self.placement_panel = PlacementPanel(self.state, on_changed=self._on_layer_changed, parent=self)
        x = self.width() - self.placement_panel.width() - 10
        y = self.placement_btn.y() + self.placement_btn.height() + 8
        self.placement_panel.move(max(10, x), y)
        self.placement_panel.show()
        self.placement_panel.raise_()

    def _on_layer_changed(self):
        self.update()

    def closeEvent(self, e):
        try:
            self.desktop_pet.show()
            self.desktop_pet.raise_()
        except Exception:
            pass
        super().closeEvent(e)

    def paintEvent(self, e):
        painter = QPainter(self)

        # ✅ 베이스: wallpaper가 선택되면 그것, 아니면 default
        wp_id = self.state.selected_bg.get("wallpaper")
        if wp_id and wp_id in self.bg_pix["wallpaper"]:
            painter.drawPixmap(0, 0, self.bg_pix["wallpaper"][wp_id])
        else:
            if not self.default_bg.isNull():
                painter.drawPixmap(0, 0, self.default_bg)
            else:
                painter.fillRect(self.rect(), Qt.white)

        # ✅ 위 레이어들
        for cat in ["wheel", "house", "deco", "flower"]:
            sel = self.state.selected_bg.get(cat)
            if sel and sel in self.bg_pix[cat]:
                painter.drawPixmap(0, 0, self.bg_pix[cat][sel])


# =========================
# Apply AI result
# =========================
def apply_ai_result(state: PetState, pet_obj, result: Dict[str, Any]):
    state.apply_delta(result.get("delta", {}))

    face = result.get("face")
    if face:
        try:
            is_low = (state.mood <= 35) or (state.joy <= 20) or (state.energy <= 20) or (state.hunger <= 18)
            sad_faces = getattr(pet_obj, "sad_faces", [])
            normal_faces = getattr(pet_obj, "normal_faces", None)
            if (not is_low) and (face in sad_faces) and normal_faces:
                face = random.choice(list(normal_faces))
        except Exception:
            pass

        if hasattr(pet_obj, "set_face"):
            pet_obj.set_face(face, hold_sec=FACE_HOLD_SEC)

    reply = result.get("reply", "")
    sec = float(result.get("bubble_sec", 2.2))
    if reply and hasattr(pet_obj, "say"):
        pet_obj.say(reply, duration=sec)

    for cmd in result.get("commands", []):
        ctype = cmd.get("type")
        if ctype == "SHAKE" and hasattr(pet_obj, "start_shake"):
            pet_obj.start_shake(sec=float(cmd.get("sec", 0.5)), strength=int(cmd.get("strength", 3)))
        elif ctype == "JUMP" and hasattr(pet_obj, "do_jump"):
            pet_obj.do_jump(int(cmd.get("strength", 12)))
        elif ctype == "SET_MODE" and hasattr(pet_obj, "set_mode"):
            pet_obj.set_mode(str(cmd.get("mode", "normal")), sec=float(cmd.get("sec", 1.5)))


# =========================
# Control Panel
# =========================
class ControlPanel(QWidget):
    def __init__(self, state: PetState, pet: PetWindow, app_icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state
        self.pet = pet
        self.ico = app_icon

        self.ai_busy = False
        self.last_needy_talk_at = 0.0

        self.setWindowTitle("Mouse Chat Panel")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if self.ico:
            self.setWindowIcon(self.ico)

        self.log = QListWidget()
        self.log.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log.setWordWrap(True)

        self.input = QTextEdit()
        self.input.setPlaceholderText("대화 입력…")
        self.input.setFixedHeight(60)
        self.input.setAcceptRichText(False)
        self.input.setLineWrapMode(QTextEdit.WidgetWidth)
        self.input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input.installEventFilter(self)

        send_btn = QPushButton("전송")
        send_btn.setMinimumWidth(60)
        send_btn.setFixedHeight(60)
        send_btn.clicked.connect(self.on_send_chat)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input, 1)
        input_row.addWidget(send_btn, 0)

        self.joy_bar = QProgressBar()
        self.joy_bar.setRange(0, 100)
        self.joy_bar.setFormat("즐거움 %p%")

        self.hunger_bar = QProgressBar()
        self.hunger_bar.setRange(0, 100)
        self.hunger_bar.setFormat("배고픔 %p%")

        self.energy_bar = QProgressBar()
        self.energy_bar.setRange(0, 100)
        self.energy_bar.setFormat("에너지 %p%")

        self.mood_bar = QProgressBar()
        self.mood_bar.setRange(0, 100)
        self.mood_bar.setFormat("기분 %p%")

        feed_btn = QPushButton("🍚 밥주기")
        pet_btn = QPushButton("🤍 쓰다듬기")
        play_btn = QPushButton("🎾 놀아주기")
        feed_btn.clicked.connect(self.on_feed)
        pet_btn.clicked.connect(self.on_pet)
        play_btn.clicked.connect(self.on_play)

        btn_row = QHBoxLayout()
        btn_row.addWidget(feed_btn)
        btn_row.addWidget(pet_btn)
        btn_row.addWidget(play_btn)

        self.money_win = MoneyWindow(self.state, icon=self.ico)
        self.home_win: Optional[HouseWindow] = None
        self.job_win = JobWindow(self.state, icon=self.ico)
        self.shop_win = ShopWindow(self.state, icon=self.ico, on_changed=self._on_shop_changed)
        self.name_win = NameWindow(self.state, icon=self.ico)

        money_btn = QPushButton("💰 소지금")
        home_btn = QPushButton("🏠 집")
        job_btn = QPushButton("🧰 알바")
        shop_btn = QPushButton("🛒 상점")
        name_btn = QPushButton("✏️ 이름")

        money_btn.clicked.connect(self.open_money)
        home_btn.clicked.connect(self.open_home)
        job_btn.clicked.connect(self.open_job)
        shop_btn.clicked.connect(self.open_shop)
        name_btn.clicked.connect(self.open_name)

        sub_row = QHBoxLayout()
        sub_row.addWidget(money_btn)
        sub_row.addWidget(home_btn)
        sub_row.addWidget(job_btn)
        sub_row.addWidget(shop_btn)
        sub_row.addWidget(name_btn)

        hint = QLabel("Enter=전송 / Shift+Enter=줄바꿈  |  드래그=이동 / ESC=종료")
        hint.setObjectName("HintLabel")

        layout = QVBoxLayout()
        layout.addWidget(self.log)
        layout.addWidget(self.joy_bar)
        layout.addWidget(self.hunger_bar)
        layout.addWidget(self.energy_bar)
        layout.addWidget(self.mood_bar)
        layout.addLayout(btn_row)
        layout.addLayout(sub_row)
        layout.addLayout(input_row)
        layout.addWidget(hint)
        self.setLayout(layout)

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.refresh)
        self.ui_timer.start(250)
        self.refresh()

        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.state_tick_1s)
        self.state_timer.start(1000)

        self.need_timer = QTimer(self)
        self.need_timer.timeout.connect(self.check_needs_and_talk)
        self.need_timer.start(900)

        self.title_timer = QTimer(self)
        self.title_timer.timeout.connect(self.update_titles)
        self.title_timer.start(400)
        self.update_titles()

    def _on_shop_changed(self):
        if self.home_win and self.home_win.isVisible():
            self.home_win.reload_bg_pixmaps()
            self.home_win.update()
        self.money_win.refresh()
        self.refresh()

    def get_active_pet(self):
        if self.home_win and self.home_win.isVisible():
            return self.home_win.house_pet
        return self.pet

    def update_titles(self):
        self.setWindowTitle(f"{self.state.pet_name} - Chat Panel")

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self.on_send_chat()
                return True
        return super().eventFilter(obj, event)

    def _calc_item_size_hint(self, text: str) -> QSize:
        w = max(260, self.log.viewport().width() - 24)
        lines = max(1, (len(text) // 28) + 1)
        h = 18 * lines + 18
        return QSize(w, h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        for i in range(self.log.count()):
            it = self.log.item(i)
            it.setSizeHint(self._calc_item_size_hint(it.text()))

    def add_log(self, who: str, msg: str):
        text = f"{who}: {msg}"
        item = QListWidgetItem(text)
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        item.setSizeHint(self._calc_item_size_hint(text))
        self.log.addItem(item)
        self.log.scrollToBottom()

    def refresh(self):
        self.state.clamp_all()
        self.joy_bar.setValue(int(self.state.joy))
        self.hunger_bar.setValue(int(self.state.hunger))
        self.energy_bar.setValue(int(self.state.energy))
        self.mood_bar.setValue(int(self.state.mood))

    def state_tick_1s(self):
        active_pet = self.get_active_pet()

        self.state.hunger -= 1.0 * DECAY_MULT
        self.state.energy -= 0.6 * DECAY_MULT

        if self.state.hunger < 25:
            self.state.mood -= 1.0 * DECAY_MULT
        if self.state.energy < 20:
            self.state.mood -= 1.0 * DECAY_MULT

        if getattr(active_pet, "sleeping", False):
            self.state.energy += 1.2
        elif getattr(active_pet, "mode", "normal") == "normal":
            self.state.energy += 0.2

        self.state.clamp_all()
        self.refresh()

        if (not getattr(active_pet, "sleeping", False)) and self.state.energy <= SLEEP_TRIGGER_ENERGY:
            if hasattr(active_pet, "start_sleep_for_60s"):
                active_pet.start_sleep_for_60s()

    def check_needs_and_talk(self):
        active_pet = self.get_active_pet()
        if getattr(active_pet, "sleeping", False):
            return

        now = time.time()
        if now - self.last_needy_talk_at < NEEDY_TALK_COOLDOWN_SEC:
            return

        who = self.state.pet_name

        if self.state.hunger <= HUNGRY_WARN_HUNGER:
            msg = random.choice(["배고파… 밥…", "찍… 배고픈데…", "밥 생각나…"])
            active_pet.say(msg, duration=2.2)
            self.add_log(who, msg)
            self.last_needy_talk_at = now
            return

        if self.state.joy <= BORED_WARN_JOY:
            msg = random.choice(["심심해…", "놀아줘…", "찍… 뭐해?"])
            active_pet.say(msg, duration=2.2)
            self.add_log(who, msg)
            self.last_needy_talk_at = now
            return

    def open_money(self):
        self.money_win.refresh()
        self.money_win.show()
        self.money_win.raise_()
        self.money_win.activateWindow()

    def open_home(self):
        if self.home_win and self.home_win.isVisible():
            self.home_win.raise_()
            self.home_win.activateWindow()
            return

        self.home_win = HouseWindow(self.state, desktop_pet=self.pet, icon=self.ico)
        self.home_win.show()
        self.home_win.raise_()
        self.home_win.activateWindow()

    def open_job(self):
        self.job_win.show()
        self.job_win.raise_()
        self.job_win.activateWindow()

    def open_shop(self):
        self.shop_win.refresh_items()
        self.shop_win.show()
        self.shop_win.raise_()
        self.shop_win.activateWindow()

    def open_name(self):
        self.name_win.edit.setText(self.state.pet_name)
        self.name_win.show()
        self.name_win.raise_()
        self.name_win.activateWindow()

    def on_send_chat(self):
        text = self.input.toPlainText().strip()
        if not text:
            return

        self.input.setPlainText("")
        self.add_log("나", text)

        if self.ai_busy:
            return

        self.ai_busy = True
        try:
            active_pet = self.get_active_pet()
            payload = {
                "event": {"type": "CHAT", "text": text, "source": "chat"},
                "state": self.state.to_dict(),
                "available_faces": active_pet.get_available_faces() if hasattr(active_pet, "get_available_faces") else self.pet.get_available_faces(),
            }
            result = call_groq_chat(payload, timeout_sec=30.0)
            apply_ai_result(self.state, active_pet, result)

            reply = result.get("reply", "")
            if reply:
                self.add_log(self.state.pet_name, reply)

            self.refresh()
        finally:
            self.ai_busy = False

    def on_feed(self):
        active_pet = self.get_active_pet()
        who = self.state.pet_name

        if getattr(active_pet, "sleeping", False):
            msg = "찍… 자는 중… (나중에…)"
            active_pet.say(msg, 2.0)
            self.add_log(who, msg)
            return

        if hasattr(active_pet, "trigger_eat_visual"):
            active_pet.trigger_eat_visual()
        self.add_log("나", "🍚 밥줬다")

        self.state.apply_delta({"hunger": +22, "joy": +3, "mood": +2, "energy": +1})
        msg = random.choice(["냠냠! 맛있다!", "찍! 밥이다!", "너무 맛있어…"])
        active_pet.say(msg, 2.2)
        self.add_log(who, msg)
        self.refresh()

    def on_pet(self):
        active_pet = self.get_active_pet()
        who = self.state.pet_name

        if getattr(active_pet, "sleeping", False):
            msg = "찍… (골골)…"
            active_pet.say(msg, 2.0)
            self.add_log(who, msg)
            return

        self.add_log("나", "🤍 쓰다듬었다")
        self.state.apply_delta({"joy": +8, "mood": +4, "energy": 0, "hunger": -1})

        if hasattr(active_pet, "start_shake"):
            active_pet.start_shake(sec=0.35, strength=2)
        msg = random.choice(["헤헤… 좋아…", "찍찍… 기분 좋아!", "쓰담쓰담 최고…"])
        active_pet.say(msg, 2.2)
        self.add_log(who, msg)
        self.refresh()

    def on_play(self):
        active_pet = self.get_active_pet()
        who = self.state.pet_name

        if getattr(active_pet, "sleeping", False):
            msg = "찍… 지금은 졸려…"
            active_pet.say(msg, 2.0)
            self.add_log(who, msg)
            return

        self.add_log("나", "🎾 놀아줬다")
        self.state.apply_delta({"joy": +10, "mood": +3, "energy": -3, "hunger": -2})

        if hasattr(active_pet, "do_jump"):
            active_pet.do_jump(13)
        if hasattr(active_pet, "set_mode"):
            active_pet.set_mode("walk", sec=1.4)

        msg = random.choice(["놀자!!", "찍찍! 신난다!", "하하! 더 놀자!"])
        active_pet.say(msg, 2.2)
        self.add_log(who, msg)
        self.refresh()


# =========================
# Main
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    app_icon = QIcon(str(APP_ICON_PATH)) if APP_ICON_PATH.exists() else None
    if app_icon:
        app.setWindowIcon(app_icon)

    # ✅ 폰트 로드
    font_dir = ASSET_DIR / "font"
    if font_dir.exists():
        ttf_list = list(font_dir.glob("*.ttf"))
        if ttf_list:
            for fp in ttf_list:
                QFontDatabase.addApplicationFont(str(fp))
        else:
            print("❌ asset/font 폴더에 .ttf가 없어:", font_dir)
    else:
        print("❌ font 폴더가 없어:", font_dir)

    load_qss(app)

    # ✅ json이 없어도 실행은 되게(폴백). 다만 안내는 찍어줌
    if not FURNITURE_JSON_PATH.exists():
        print("⚠️ furniture.json이 없어! 폴더 스캔 폴백으로 실행 중:", FURNITURE_JSON_PATH)

    state = PetState()
    pet = PetWindow(state, app_icon=app_icon)
    panel = ControlPanel(state, pet, app_icon=app_icon)

    pet.show()
    panel.show()

    sys.exit(app.exec())