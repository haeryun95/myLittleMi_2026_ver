# =========================
# Standard Library
# =========================
import sys
import os
import time
import json
import random
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Any, List, Optional, Set, Tuple

# =========================
# PySide6
# =========================
from PySide6.QtCore import Qt, QEvent, QTimer, QPoint, QRect, QSize
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPixmap, QPainter, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QProgressBar,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QTextEdit,
    QLineEdit,
    QFrame,
    QMessageBox,
    QStackedWidget,
    QSpinBox
)

# =========================
# ✅ Groq Direct Settings
# =========================
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = "앱키"  # TODO: 키 넣기
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

# ✅ 배경/가구
BG_DIR = ASSET_DIR / "background"
BG_DEFAULT_PATH = BG_DIR / "default.png"
FURNITURE_JSON_PATH = BG_DIR / "furniture.json"
HOUSE_BG_PATH = BG_DIR / "hamsterHouse.png"  # 구버전 호환(필요시)

# ✅ 알바/아이템
JOBS_JSON_PATH = ASSET_DIR / "jobs.json"
ITEMS_JSON_PATH = ASSET_DIR / "items.json"

# =========================
# UI/Window Tunings
# =========================
HOUSE_WIN_W = 620
HOUSE_WIN_H = int(HOUSE_WIN_W * 864 / 1184)
HOUSE_SCALE_CHAR = 0.33
HOUSE_SCALE_BUBBLE = 0.15

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
BORED_WARN_FUN = 12.0
NEEDY_TALK_COOLDOWN_SEC = 18.0
WANDER_INTERVAL_MS_RANGE = (3_000, 7_000)

# =========================
# ✅ House Furniture / Layers
# =========================
BG_CATEGORIES = ["wallpaper", "wheel", "house", "deco", "flower"]
BG_LAYER_ORDER = ["wallpaper", "wheel", "house", "deco", "flower"]

PLACEMENT_PANEL_W = 420
PLACEMENT_PANEL_H = 520
THUMB_SIZE = 84
ROW_HEIGHT = 98
CAT_BTN_H = 36
CAT_BTN_MIN_W = 72

SHOP_THUMB_SIZE = 72
SHOP_ROW_HEIGHT = 92

PINK = "#ff4fa3"

# =========================
# QSS loader
# =========================
def load_qss(app: QApplication):
    if QSS_PATH.exists():
        app.setStyleSheet(QSS_PATH.read_text(encoding="utf-8"))

# =========================
# Helpers
# =========================
def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))

def safe_read_json(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

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

def scan_bg_items_fallback() -> Dict[str, Dict[str, Path]]:
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
                out[cat].append({"id": iid, "name": name, "price": price, "file": file_rel})
        return out

    scanned = scan_bg_items_fallback()
    out2: Dict[str, List[dict]] = {cat: [] for cat in BG_CATEGORIES}
    for cat in BG_CATEGORIES:
        for iid, p in scanned.get(cat, {}).items():
            base_price = {"wallpaper": 900, "wheel": 700, "house": 1200, "deco": 600, "flower": 500}.get(cat, 600)
            price = int(base_price + min(400, len(iid) * 10))
            rel = f"{cat}/{p.name}"
            out2[cat].append({"id": iid, "name": iid, "price": price, "file": rel})
    return out2

def resolve_bg_path(file_rel: str) -> Path:
    return (BG_DIR / file_rel).resolve()

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
            "delta": {"fun": 1, "mood": 0, "energy": 0, "hunger": 0},
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
state: hunger/energy/max_energy/mood/fun/last_face/pet_name/money
available_faces: string[]

────────────────────────
[출력 스키마 - 키 이름 변경 금지]
{
"reply": string,
"face": string,
"bubble_sec": number,
"delta": {"fun": number,"mood": number,"energy": number,"hunger": number, "max_energy": number?},
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
                "delta": {"fun": 1, "mood": 0, "energy": 0, "hunger": 0},
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
        "delta": {"fun": 0, "mood": -1, "energy": 0, "hunger": 0},
        "commands": [],
    }

# =========================
# State
# =========================
def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))

class PetState:
    """
    ✅ mood 유지 + fun 분리
    ✅ energy/max_energy (stamina 역할)
    ✅ JobWindow 기대(stats/inventory)도 state가 기본 보유
    """
    # 숫자 -> 라벨 구간(원하는대로 수정 가능)
    MOOD_BANDS: List[Tuple[int, str]] = [
        (15, "절망"),
        (30, "우울"),
        (45, "슬픔"),
        (55, "무덤덤"),
        (70, "기분좋음"),
        (85, "행복"),
        (101, "기쁨"),  # 상한 포함용
    ]

    def __init__(self):
        self.pet_name = "라이미"

        self.energy = 100.0
        self.max_energy = 150.0

        self.hunger = 60.0
        self.fun = 70.0

        # ✅ mood는 숫자로 저장 (표시는 라벨로)
        self.mood = 70.0

        # 알바/아이템용 능력치(필요한 만큼)
        self.stats: Dict[str, int] = {
            "power": 0,
            "cute": 5,
            "fun": 0,   # 알바용 보너스(아이템으로 올릴 수 있음)
        }
        self.inventory: Dict[str, int] = {}

        self.money = 0
        self.last_face = "normal01"

        # ✅ 배경/가구
        self.owned_bg: Dict[str, Set[str]] = {cat: set() for cat in BG_CATEGORIES}
        self.selected_bg: Dict[str, Optional[str]] = {cat: None for cat in BG_CATEGORIES}

    # -------------------------
    # ✅ 표시용: 숫자 mood -> 상태 라벨
    # -------------------------
    @property
    def mood_label(self) -> str:
        v = int(round(clamp(self.mood)))
        for limit, name in self.MOOD_BANDS:
            if v < limit:
                return name
        return self.MOOD_BANDS[-1][1]

    # -------------------------
    # ✅ mood 갱신: fun/energy/hunger 영향 반영
    # 호출 타이밍:
    #  - 1초/2초 타이머 틱마다
    #  - 행동(밥먹기/놀기/알바) 끝날 때
    # -------------------------
    def update_mood_from_needs(self, dt_sec: float = 1.0) -> None:
        """
        dt_sec: 시간 경과(초). 타이머틱이면 1.0 주면 됨.
        """

        # 1) 정규화(0~1)
        fun_n = clamp(self.fun) / 100.0
        # energy는 0~max_energy라서 max 기준 정규화
        energy_n = clamp(self.energy, 0.0, self.max_energy) / float(self.max_energy)
        hunger_n = clamp(self.hunger) / 100.0  # 너는 hunger가 높을수록 배고픈 값이라면 아래 반대로 바꿔야 함

        # ⚠️ 만약 hunger가 "배고픔(높을수록 나쁨)"이면:
        # hunger_good = 1.0 - hunger_n
        # 지금 예시는 hunger가 "포만감(높을수록 좋음)"이라는 가정으로 감.
        hunger_good = hunger_n

        # 2) mood 목표치 계산 (0~100)
        # 가중치는 취향대로 조절해도 됨
        # - fun: 즉각 기분을 올려주는 힘
        # - energy: 낮으면 짜증/우울 쪽으로 끌고감
        # - hunger: 배고프면 기분 나빠지는 느낌(옵션)
        base = 50.0
        target = (
            base
            + (fun_n - 0.5) * 70.0          # fun 영향 (±35 정도)
            + (energy_n - 0.5) * 50.0       # energy 영향 (±25 정도)
            + (hunger_good - 0.5) * 30.0    # hunger 영향 (±15 정도)
        )
        target = clamp(target)

        # 3) 스무딩: 현재 mood가 목표치를 천천히 따라감
        # dt_sec 커질수록 더 빨리 따라가게(프레임 독립)
        follow_speed_per_sec = 6.0  # 초당 최대 몇 포인트 따라갈지 느낌
        max_step = follow_speed_per_sec * max(0.0, dt_sec)

        diff = target - self.mood
        step = clamp(diff, -max_step, max_step)

        self.mood = clamp(self.mood + step)

    # -------------------------
    # ✅ "행동"이 mood에 직접 주는 영향도 같이 쓰고 싶으면
    # -------------------------
    def add_fun(self, amount: float) -> None:
        self.fun = clamp(self.fun + amount)
        # fun 변했으니 mood도 한번 반영
        self.update_mood_from_needs(dt_sec=0.5)

    def add_energy(self, amount: float) -> None:
        self.energy = clamp(self.energy + amount, 0.0, self.max_energy)
        self.update_mood_from_needs(dt_sec=0.5)
    
    def clamp_all(self) -> None:
        # 기본 욕구/리소스 clamp
        self.energy = clamp(self.energy, 0.0, self.max_energy)
        self.hunger = clamp(self.hunger)   # 0~100
        self.fun = clamp(self.fun)         # 0~100
        self.mood = clamp(self.mood)       # 0~100

        # stats/inventory 정리
        if not isinstance(self.stats, dict):
            self.stats = {"power": 0, "cute": 5, "fun": 0}
        for k in ("power", "cute", "fun"):
            self.stats[k] = int(self.stats.get(k, 0))

        if not isinstance(self.inventory, dict):
            self.inventory = {}
        # 음수 수량 방지
        for k in list(self.inventory.keys()):
            self.inventory[k] = max(0, int(self.inventory[k]))
            if self.inventory[k] == 0:
                # 0이면 지우고 싶으면 이 줄 켜도 됨
                # del self.inventory[k]
                pass


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
        self.money_label.setText(f"현재 소지금: {int(self.state.money)}원")

# =========================
# Job Window (JSON 기반: 장소 선택/텍스트RPG/드랍/판매)
# =========================
# ✅ 파일 경로 (기본값)
JOBS_JSON_PATH = ASSET_DIR / "jobs.json"
ITEMS_JSON_PATH = ASSET_DIR / "items.json"

# ✅ 스크립트 길이
SCRIPT_LINES_DEFAULT = 10
SCRIPT_LINES_RANGE = (8, 12)

PINK = "#ff4fa3"

# ✅ 알바 “능력치” 라벨 (state.stats에 있는 것만)
STAT_LABELS = {
    "power": "힘",
    "fun": "흥미도",
    "cute": "귀여움",
}
# ✅ 기본 욕구/리소스(바)는 따로: energy / mood / fun(욕구) / hunger


class JobWindow(QWidget):
    def __init__(
        self,
        state,  # PetState
        icon: Optional[QIcon] = None,
        jobs_json_path: Path = JOBS_JSON_PATH,
        items_json_path: Path = ITEMS_JSON_PATH,
        close_on_exhaust: bool = True,
        script_random_lines: bool = True
    ):
        super().__init__()
        self.state = state
        self.jobs_json_path = Path(jobs_json_path)
        self.items_json_path = Path(items_json_path)
        self.close_on_exhaust = bool(close_on_exhaust)
        self.script_random_lines = bool(script_random_lines)

        self.setWindowTitle("알바")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if icon:
            self.setWindowIcon(icon)

        # -------------------------
        # 데이터
        # -------------------------
        self.jobs_data: Dict[str, Any] = {}
        self.items_db: Dict[str, Any] = {}
        self.places: List[Dict[str, Any]] = []

        # -------------------------
        # 진행 상태
        # -------------------------
        self.current_place: Optional[Dict[str, Any]] = None
        self.script_lines: List[str] = []
        self.script_i = 0
        self.running = False

        self.timer = QTimer(self)
        self.timer.setInterval(900)
        self.timer.timeout.connect(self._tick_script)

        # -------------------------
        # UI Stack (선택 / 진행 / 판매)
        # -------------------------
        self.stack = QStackedWidget()

        self._stats_label_sets: List[Dict[str, QLabel]] = []
        self._money_labels: List[QLabel] = []
        self._need_labels: List[Dict[str, QLabel]] = []  # energy/mood/fun/hunger

        # ===== page_select =====
        self.page_select = QWidget()
        v1 = QVBoxLayout(self.page_select)
        v1.setSpacing(10)

        v1.addWidget(self._build_stats_bar())

        self.place_list = QListWidget()
        self.place_list.setSpacing(8)
        self.place_list.itemClicked.connect(self._on_click_place)
        v1.addWidget(self.place_list, 1)

        row1 = QHBoxLayout()
        self.btn_open_sell = QPushButton("인벤토리 / 판매")
        self.btn_open_sell.clicked.connect(self._open_sell_page)
        row1.addWidget(self.btn_open_sell)

        self.btn_reload = QPushButton("새로고침")
        self.btn_reload.clicked.connect(self._reload_all_ui)
        row1.addWidget(self.btn_reload)

        row1.addStretch(1)
        v1.addLayout(row1)

        self.hint = QLabel("장소를 선택해줘.")
        self.hint.setObjectName("HintLabel")
        v1.addWidget(self.hint)

        # ===== page_run =====
        self.page_run = QWidget()
        v2 = QVBoxLayout(self.page_run)
        v2.setSpacing(10)

        v2.addWidget(self._build_stats_bar())

        self.run_title = QLabel("")
        self.run_title.setStyleSheet("font-size: 16px; font-weight: 900;")
        v2.addWidget(self.run_title)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        v2.addWidget(self.log, 1)

        row2 = QHBoxLayout()
        self.btn_stop = QPushButton("중단")
        self.btn_stop.clicked.connect(self._stop_and_back)
        row2.addWidget(self.btn_stop)

        self.btn_skip = QPushButton("빠르게 끝내기")
        self.btn_skip.clicked.connect(self._finish_immediately)
        row2.addWidget(self.btn_skip)

        self.btn_back = QPushButton("목록으로")
        self.btn_back.clicked.connect(self._stop_and_back)
        row2.addWidget(self.btn_back)

        v2.addLayout(row2)

        self.result = QLabel("")
        self.result.setObjectName("HintLabel")
        v2.addWidget(self.result)

        # ===== page_sell =====
        self.page_sell = QWidget()
        v3 = QVBoxLayout(self.page_sell)
        v3.setSpacing(10)

        v3.addWidget(self._build_stats_bar())

        top = QHBoxLayout()
        t = QLabel("🧺 인벤토리 판매")
        t.setStyleSheet("font-size: 16px; font-weight: 900;")
        top.addWidget(t)

        self.btn_back_to_jobs = QPushButton("알바 목록")
        self.btn_back_to_jobs.clicked.connect(lambda: self.stack.setCurrentWidget(self.page_select))
        top.addWidget(self.btn_back_to_jobs)
        v3.addLayout(top)

        self.inv_list = QListWidget()
        self.inv_list.setSpacing(8)
        self.inv_list.itemClicked.connect(self._on_click_inv_item)
        v3.addWidget(self.inv_list, 1)

        sell_row = QHBoxLayout()
        self.sell_hint = QLabel("판매할 아이템을 선택해줘.")
        self.sell_hint.setObjectName("HintLabel")
        sell_row.addWidget(self.sell_hint, 1)

        self.sell_qty = QSpinBox()
        self.sell_qty.setRange(1, 9999)
        self.sell_qty.setValue(1)
        self.sell_qty.valueChanged.connect(self._update_sell_preview)
        sell_row.addWidget(QLabel("수량:"))
        sell_row.addWidget(self.sell_qty)

        self.btn_sell = QPushButton("판매")
        self.btn_sell.clicked.connect(self._sell_selected)
        sell_row.addWidget(self.btn_sell)
        v3.addLayout(sell_row)

        self.sell_preview = QLabel("총 판매 예상액: 0원")
        self.sell_preview.setObjectName("HintLabel")
        v3.addWidget(self.sell_preview)

        self.sell_result = QLabel("")
        self.sell_result.setObjectName("HintLabel")
        v3.addWidget(self.sell_result)

        # stack 등록
        self.stack.addWidget(self.page_select)
        self.stack.addWidget(self.page_run)
        self.stack.addWidget(self.page_sell)

        lay = QVBoxLayout(self)
        lay.addWidget(self.stack)

        # 초기 로드
        self._reload_all_ui()
        self.stack.setCurrentWidget(self.page_select)

        # 돈/스탯 UI 자동 갱신
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._refresh_stats_ui)
        self.ui_timer.start(400)

    # -------------------------
    # ✅ stamina → energy 매핑
    # -------------------------
    def _norm_key(self, k: str) -> str:
        return "energy" if k == "stamina" else k

    def _get_need_stats(self) -> Dict[str, int]:
        # PetState의 float → 표시용 int
        return {
            "energy": int(getattr(self.state, "energy", 0)),
            "max_energy": int(getattr(self.state, "max_energy", 0)),
            "hunger": int(getattr(self.state, "hunger", 0)),
            "fun_need": int(getattr(self.state, "fun", 0)),   # ✅ 욕구 fun
            "mood": int(getattr(self.state, "mood", 0)),
        }

    # -------------------------
    # 내장 헬퍼들
    # -------------------------
    def _safe_read_json(self, path: Path) -> Optional[Any]:
        try:
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _load_json_file(self, path: Path, default: dict) -> dict:
        data = self._safe_read_json(path)
        return data if isinstance(data, dict) else default

    def _item_info(self, item_id: str) -> Dict[str, Any]:
        return ((self.items_db.get("items") or {}).get(item_id) or {})

    def _item_name(self, item_id: str) -> str:
        return self._item_info(item_id).get("name") or item_id

    def _item_effects(self, item_id: str) -> Dict[str, int]:
        return self._item_info(item_id).get("effects") or {}

    def _item_icon(self, item_id: str) -> Optional[str]:
        p = self._item_info(item_id).get("icon")
        return p if p else None

    def _item_sell_price(self, item_id: str) -> int:
        return int(self._item_info(item_id).get("sell_price") or 0)

    def _item_rarity(self, item_id: str) -> str:
        return str(self._item_info(item_id).get("rarity") or "common").lower()

    def _rarity_fx(self, rarity: str) -> str:
        r = (rarity or "common").lower()
        if r == "legendary": return "🌈✨ 레전더리 획득!!"
        if r == "epic":      return "💜✨ 에픽 획득!"
        if r == "rare":      return "💛✨ 레어 획득!"
        if r == "uncommon":  return "💚 희귀한 아이템 획득!"
        return ""

    def _calc_item_bonus(self, inventory: Dict[str, int]) -> Dict[str, int]:
        bonus: Dict[str, int] = {k: 0 for k in STAT_LABELS.keys()}
        for item_id, count in (inventory or {}).items():
            count = int(count)
            if count <= 0:
                continue
            eff = self._item_effects(item_id)
            for stat, v in (eff or {}).items():
                stat = self._norm_key(stat)
                if stat in bonus:
                    bonus[stat] = int(bonus.get(stat, 0)) + int(v) * count
        return bonus

    def _merged_stats(self, base: Dict[str, int], bonus: Dict[str, int]) -> Dict[str, int]:
        out = dict(base or {})
        for k, v in (bonus or {}).items():
            out[k] = int(out.get(k, 0)) + int(v)
        # ✅ 요구치가 stamina로 들어오면 energy로 체크해야 하니까 total에 energy도 넣어둠
        out["energy"] = int(getattr(self.state, "energy", 0))
        return out

    def _meets_requirements(self, total_stats: Dict[str, int], req: Dict[str, int]) -> Tuple[bool, List[str]]:
        lacks: List[str] = []
        for stat, need in (req or {}).items():
            stat = self._norm_key(stat)
            cur = int(total_stats.get(stat, 0))
            if cur < int(need):
                if stat == "energy":
                    lacks.append(f"에너지 {need} 필요(현재 {cur})")
                else:
                    lacks.append(f"{STAT_LABELS.get(stat, stat)} {need} 필요(현재 {cur})")
        return (len(lacks) == 0), lacks

    def _resolve_drop_table(self, place: Dict[str, Any]) -> List[Dict[str, Any]]:
        if place.get("drop_table"):
            return place.get("drop_table") or []
        cat_id = place.get("category")
        cats = self.jobs_data.get("categories") or {}
        cat = cats.get(cat_id) or {}
        return cat.get("drop_table") or []

    def _roll_items_from_table(self, drop_table: List[Dict[str, Any]]) -> Dict[str, int]:
        got: Dict[str, int] = {}
        for it in (drop_table or []):
            item_id = it.get("id")
            if not item_id:
                continue
            chance = float(it.get("chance", 0))
            if random.random() <= chance:
                mn = int(it.get("min", 1))
                mx = int(it.get("max", mn))
                qty = random.randint(mn, mx)
                got[item_id] = got.get(item_id, 0) + qty
        return got

    def _roll_money(self, range_pair) -> int:
        if isinstance(range_pair, list) and len(range_pair) == 2:
            return random.randint(int(range_pair[0]), int(range_pair[1]))
        return int(range_pair or 0)

    # -------------------------
    # UI - stats bar
    # -------------------------
    def _build_stats_bar(self) -> QFrame:
        wrap = QFrame()
        wrap.setFrameShape(QFrame.StyledPanel)
        row = QHBoxLayout(wrap)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(12)

        money = QLabel("")
        money.setStyleSheet("font-weight: 900;")
        row.addWidget(money)
        self._money_labels.append(money)

        # ✅ energy/mood/fun/hunger 표시
        need_labels: Dict[str, QLabel] = {}
        for key in ["energy", "mood", "fun_need", "hunger"]:
            lb = QLabel()
            lb.setMinimumWidth(110)
            need_labels[key] = lb
            row.addWidget(lb)
        self._need_labels.append(need_labels)

        # ✅ 알바 능력치(power/cute/fun bonus)
        labels: Dict[str, QLabel] = {}
        for k in STAT_LABELS.keys():
            lb = QLabel()
            lb.setTextFormat(Qt.RichText)
            lb.setMinimumWidth(120)
            labels[k] = lb
            row.addWidget(lb)

        self._stats_label_sets.append(labels)
        row.addStretch(1)
        return wrap

    def _refresh_stats_ui(self):
        for ml in self._money_labels:
            ml.setText(f"💰 {int(getattr(self.state, 'money', 0))}원")

        need = self._get_need_stats()
        for d in self._need_labels:
            d["energy"].setText(f"에너지: {need['energy']}/{need['max_energy']}")
            d["mood"].setText(f"기분: {need['mood']}")
            d["fun_need"].setText(f"재미: {need['fun_need']}")
            d["hunger"].setText(f"허기: {need['hunger']}")

        base = getattr(self.state, "stats", {k: 0 for k in STAT_LABELS.keys()})
        inv = getattr(self.state, "inventory", {})
        bonus = self._calc_item_bonus(inv)

        for labels in self._stats_label_sets:
            for key, lb in labels.items():
                b = int(base.get(key, 0))
                plus = int(bonus.get(key, 0))
                if plus > 0:
                    lb.setText(f"{STAT_LABELS[key]}: {b} <span style='color:{PINK}; font-weight:900'>+{plus}</span>")
                else:
                    lb.setText(f"{STAT_LABELS[key]}: {b}")

    # -------------------------
    # data load + ui reload
    # -------------------------
    def _load_data(self):
        missing = []
        if not self.jobs_json_path.exists():
            missing.append(f"❌ JSON 없음: {self.jobs_json_path}")
        if not self.items_json_path.exists():
            missing.append(f"❌ JSON 없음: {self.items_json_path}")
        if missing:
            self.hint.setText("\n".join(missing))

        self.jobs_data = self._load_json_file(self.jobs_json_path, {"categories": {}, "places": []})
        self.items_db = self._load_json_file(self.items_json_path, {"items": {}})
        self.places = self.jobs_data.get("places", []) or []

        # state 보장
        if not hasattr(self.state, "stats") or not isinstance(self.state.stats, dict):
            self.state.stats = {k: 0 for k in STAT_LABELS.keys()}
        for k in STAT_LABELS.keys():
            self.state.stats.setdefault(k, 0)

        if not hasattr(self.state, "inventory") or not isinstance(self.state.inventory, dict):
            self.state.inventory = {}

    def _reload_all_ui(self):
        self._load_data()
        self._refresh_stats_ui()
        self._reload_places()
        self._refresh_inventory_ui()

    # -------------------------
    # places list
    # -------------------------
    def _reload_places(self):
        self.place_list.clear()

        if not self.places:
            it = QListWidgetItem("알바 장소가 없어… (jobs.json places 확인)")
            it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.place_list.addItem(it)
            self.place_list.setIconSize(QSize(64, 64))
            return

        base = self.state.stats
        bonus = self._calc_item_bonus(self.state.inventory)
        total = self._merged_stats(base, bonus)  # ✅ total["energy"] 포함됨

        for p in self.places:
            name = p.get("name", "이름없음")
            req = p.get("requirements", {}) or {}
            ok, _ = self._meets_requirements(total, req)

            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, p)

            # 썸네일
            thumb_path = p.get("thumb")
            if thumb_path:
                abs_path = (BASE_DIR / str(thumb_path)).resolve() if not os.path.isabs(str(thumb_path)) else Path(str(thumb_path))
                pm = QPixmap(str(abs_path))
                if not pm.isNull():
                    it.setIcon(QIcon(pm))

            # tooltip
            money_rng = p.get("reward_money", [0, 0])
            if isinstance(money_rng, list) and len(money_rng) == 2:
                money_txt = f"{money_rng[0]}~{money_rng[1]}원"
            else:
                money_txt = f"{money_rng}원"

            # ✅ tooltip 요구치도 stamina면 energy로 표기
            pretty_req = []
            for k, v in req.items():
                k2 = self._norm_key(k)
                if k2 == "energy":
                    pretty_req.append(f"에너지 {v}")
                else:
                    pretty_req.append(f"{STAT_LABELS.get(k2,k2)} {v}")
            req_txt = ", ".join(pretty_req) or "없음"

            drop_table = self._resolve_drop_table(p)
            preview = []
            for d in drop_table[:3]:
                did = d.get("id")
                if not did:
                    continue
                ch = float(d.get("chance", 0)) * 100
                preview.append(f"{self._item_name(did)}({ch:.1f}%)")
            drop_txt = ", ".join(preview) + ("..." if len(drop_table) > 3 else "")
            if not drop_txt:
                drop_txt = "없음"

            tip = f"요구: {req_txt}\n보상: {money_txt}\n드랍: {drop_txt}"
            if not ok:
                tip += "\n🔒 잠김"
            it.setToolTip(tip)

            if not ok:
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
                it.setForeground(Qt.gray)

            self.place_list.addItem(it)

        self.place_list.setIconSize(QSize(64, 64))

    def _on_click_place(self, item: QListWidgetItem):
        place = item.data(Qt.UserRole)
        if not isinstance(place, dict):
            return

        base = self.state.stats
        bonus = self._calc_item_bonus(self.state.inventory)
        total = self._merged_stats(base, bonus)

        ok, lacks = self._meets_requirements(total, place.get("requirements", {}) or {})
        if not ok:
            QMessageBox.information(self, "조건 부족", "갈 수 없어!\n" + "\n".join(lacks))
            return

        self._start_job(place)

    # -------------------------
    # run (text rpg)
    # -------------------------
    def _start_job(self, place: Dict[str, Any]):
        self.current_place = place

        lines = list(place.get("script", []) or [])
        if not lines:
            lines = ["일을 시작했다.", "열심히 일하는 중…", "퇴근했다!"]

        random.shuffle(lines)

        if self.script_random_lines:
            n = random.randint(SCRIPT_LINES_RANGE[0], SCRIPT_LINES_RANGE[1])
        else:
            n = SCRIPT_LINES_DEFAULT

        self.script_lines = lines[:n]
        self.script_i = 0
        self.running = True

        self.run_title.setText(f"📍 {place.get('name','')}")
        self.log.clear()
        self.result.setText("")

        self._refresh_stats_ui()
        self.stack.setCurrentWidget(self.page_run)

        self.timer.stop()
        self.timer.start()

    def _tick_script(self):
        if not self.running or not self.current_place:
            self.timer.stop()
            return

        if self.script_i < len(self.script_lines):
            self.log.append(self.script_lines[self.script_i])
            self.script_i += 1
            return

        self.timer.stop()
        self.running = False
        self._apply_rewards(self.current_place)

    def _finish_immediately(self):
        if not self.current_place:
            return
        while self.script_i < len(self.script_lines):
            self.log.append(self.script_lines[self.script_i])
            self.script_i += 1
        self.timer.stop()
        self.running = False
        self._apply_rewards(self.current_place)

    def _stop_and_back(self):
        self.timer.stop()
        self.running = False
        self.current_place = None
        self.stack.setCurrentWidget(self.page_select)
        self._refresh_stats_ui()
        self._reload_places()

    def _apply_rewards(self, place: Dict[str, Any]):
        delta = dict(place.get("delta", {}) or {})

        # ✅ stamina가 있으면 energy로 합치기
        if "stamina" in delta and "energy" not in delta:
            delta["energy"] = delta["stamina"]

        energy_cost = float(delta.get("energy", 0))  # 보통 -6 같은 값
        after_energy = float(getattr(self.state, "energy", 0.0)) + energy_cost

        # -------------------------
        # ✅ 탈진 체크: energy 기준
        # -------------------------
        if after_energy < 0:
            QMessageBox.warning(self, "탈진!", "에너지가 바닥나서 쓰러졌어…\n알바를 중단하고 돌아갈게!")
            self.state.energy = 0.0
            self.result.setText("에너지 부족으로 알바 실패… (보상 없음)")
            self._stop_and_back()
            if self.close_on_exhaust:
                self.close()
            return

        # -------------------------
        # ✅ 정상 완료: 돈/드랍/스탯 반영
        # -------------------------
        money = self._roll_money(place.get("reward_money", [0, 0]))
        self.state.money += int(money)

        drop_table = self._resolve_drop_table(place)
        got_items = self._roll_items_from_table(drop_table)

        for item_id, qty in got_items.items():
            self.state.inventory[item_id] = int(self.state.inventory.get(item_id, 0)) + int(qty)

        # 레어 연출 로그
        for item_id, qty in got_items.items():
            fx = self._rarity_fx(self._item_rarity(item_id))
            if fx:
                self.log.append(f"{fx}  {self._item_name(item_id)} x{qty}")

        # ✅ delta 적용:
        # - energy/mood/fun/hunger는 PetState 본체에
        # - power/cute/fun(알바능력)은 state.stats에
        for k, v in delta.items():
            k2 = self._norm_key(k)
            if k2 == "energy":
                self.state.energy = max(0.0, float(self.state.energy) + float(v))
                self.state.energy = min(float(self.state.max_energy), float(self.state.energy))
            elif k2 == "mood":
                self.state.mood = max(0.0, min(100.0, float(self.state.mood) + float(v)))
            elif k2 == "hunger":
                self.state.hunger = max(0.0, min(100.0, float(self.state.hunger) + float(v)))
            elif k2 == "fun":
                # ⚠️ jobs.json delta.fun은 “욕구 재미”로 처리 (원하면 stats쪽으로 바꿔줄 수 있음)
                self.state.fun = max(0.0, min(100.0, float(self.state.fun) + float(v)))
            elif k2 in self.state.stats:
                self.state.stats[k2] = int(self.state.stats.get(k2, 0)) + int(v)

        # 결과 표시
        if got_items:
            item_txt = ", ".join([f"{self._item_name(k)} x{v}" for k, v in got_items.items()])
        else:
            item_txt = "없음"

        self.result.setText(f"알바 완료! (+{money}원) / 아이템: {item_txt}")

        self._refresh_stats_ui()
        self._reload_places()
        self._refresh_inventory_ui()

    # -------------------------
    # sell (inventory)
    # -------------------------
    def _open_sell_page(self):
        self._refresh_stats_ui()
        self._refresh_inventory_ui()
        self.sell_result.setText("")
        self.sell_preview.setText("총 판매 예상액: 0원")
        self.stack.setCurrentWidget(self.page_sell)

    def _refresh_inventory_ui(self):
        self.inv_list.clear()

        inv = self.state.inventory or {}
        for item_id, qty in inv.items():
            qty = int(qty)
            if qty <= 0:
                continue

            name = self._item_name(item_id)
            price = self._item_sell_price(item_id)
            rarity = self._item_rarity(item_id)

            it = QListWidgetItem(f"{name}  x{qty}   (판매가 {price}원)")
            it.setData(Qt.UserRole, {"id": item_id, "qty": qty})

            icon_path = self._item_icon(item_id)
            if icon_path:
                p = (BASE_DIR / icon_path).resolve() if not os.path.isabs(icon_path) else Path(icon_path)
                pm = QPixmap(str(p))
                if not pm.isNull():
                    it.setIcon(QIcon(pm))

            if rarity in ("rare", "epic", "legendary"):
                it.setForeground(Qt.darkYellow)

            it.setToolTip(f"희귀도: {rarity}\n판매가: {price}원")
            self.inv_list.addItem(it)

        self.inv_list.setIconSize(QSize(40, 40))

    def _on_click_inv_item(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole) or {}
        item_id = data.get("id")
        have = int(data.get("qty") or 1)

        self.sell_qty.setRange(1, max(1, have))
        self.sell_qty.setValue(1)

        name = self._item_name(item_id)
        price = self._item_sell_price(item_id)
        self.sell_hint.setText(f"선택: {name} (1개 {price}원)")

        self._update_sell_preview()

    def _update_sell_preview(self):
        item = self.inv_list.currentItem()
        if not item:
            self.sell_preview.setText("총 판매 예상액: 0원")
            return

        data = item.data(Qt.UserRole) or {}
        item_id = data.get("id")
        have = int(data.get("qty") or 0)
        if not item_id or have <= 0:
            self.sell_preview.setText("총 판매 예상액: 0원")
            return

        qty = int(self.sell_qty.value())
        qty = min(qty, have)

        price = self._item_sell_price(item_id)
        total = max(0, price * qty)
        self.sell_preview.setText(f"총 판매 예상액: {total}원")

    def _sell_selected(self):
        sel = self.inv_list.currentItem()
        if not sel:
            QMessageBox.information(self, "판매", "판매할 아이템을 선택해줘.")
            return

        data = sel.data(Qt.UserRole) or {}
        item_id = data.get("id")
        have = int(data.get("qty") or 0)
        qty = int(self.sell_qty.value())
        qty = min(qty, have)

        if not item_id or qty <= 0:
            return

        price = self._item_sell_price(item_id)
        if price <= 0:
            QMessageBox.information(self, "판매", "이 아이템은 판매할 수 없어.")
            return

        total = price * qty

        self.state.inventory[item_id] = max(0, int(self.state.inventory.get(item_id, 0)) - qty)
        self.state.money += int(total)

        name = self._item_name(item_id)
        self.sell_result.setText(f"판매 완료! {name} x{qty} → +{total}원")

        self._refresh_stats_ui()
        self._refresh_inventory_ui()
        self._reload_places()
        self.sell_preview.setText("총 판매 예상액: 0원")

# =========================
# Name Window
# =========================
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
        name = self.edit.text().strip() or "라이미"
        self.state.pet_name = name[:12]
        self.close()

# =========================
# ✅ Thumbnail row widget
# =========================
class ThumbRow(QWidget):
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
# Placement Panel
# =========================
class PlacementPanel(QWidget):
    def __init__(self, state: PetState, on_changed=None, parent=None):
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
                    padding: 6px 8px;
                    border-radius: 12px;
                    border: 1px solid rgba(0,0,0,55);
                    background: rgba(220,240,255,245);
                    font-weight: 900;
                }
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
# Shop Window (Furniture)
# =========================
class ShopWindow(SimpleWindow):
    def __init__(self, state: PetState, icon: Optional[QIcon] = None, on_changed=None):
        super().__init__("상점", icon=icon)
        self.state = state
        self.on_changed = on_changed

        # 간식 버튼 (펫 상태에 영향)
        btn = QPushButton("간식 사기 (-300원, 배고픔 +10, 재미 +3, 기분 +1)")
        btn.clicked.connect(self.buy_snack)
        self.layout().addWidget(btn)

        furn_title = QLabel("🪑 가구 구매 (json 기반)")
        furn_title.setObjectName("TitleLabel")
        self.layout().addWidget(furn_title)

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
        return None if pm.isNull() else pm

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
            self.shop_list.addItem(QListWidgetItem("구매할 가구가 없어!"))
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
        self.state.apply_delta({"hunger": +10, "fun": +3, "mood": +1, "energy": +1})
        self.result.setText("간식 샀다! (배고픔+10, 재미+3, 기분+1)")
        self._changed()

    def buy_bg_item(self, cat: str, iid: str, name: str, price: int, file_rel: str):
        if price > 0 and self.state.money < price:
            self.result.setText("돈이 부족해…")
            return
        if file_rel:
            p = resolve_bg_path(file_rel)
            if not p.exists():
                self.result.setText("이미지 파일이 없어…(json 경로 확인)")
                return

        self.state.money -= max(0, int(price))
        self.state.owned_bg[cat].add(iid)

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

        bubble = QPixmap(str(BUBBLE_PATH))
        if bubble.isNull():
            self.bubble = None
        else:
            self.bubble = bubble.scaled(
                int(bubble.width() * SCALE_BUBBLE),
                int(bubble.height() * SCALE_BUBBLE),
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
        self.state.apply_delta({"fun": +3, "mood": +6, "energy": 0, "hunger": -0.5})

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
            self.state.fun = clamp(self.state.fun + 2)
            self.say("찍! 좀 나아졌어…", duration=2.2)
            self.set_mode("normal", sec=99999)

        if self.mode == "normal" and now > self.face_until and now >= self.next_normal_change:
            low = (self.state.mood <= 35) or (self.state.fun <= 20) or (self.state.energy <= 20) or (self.state.hunger <= 18)
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
# HousePetWidget (Inside House)
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
            self.state.fun = clamp(self.state.fun + 2)
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
# House Window
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

        self.bg_pix: Dict[str, Dict[str, QPixmap]] = {cat: {} for cat in BG_CATEGORIES}
        self.reload_bg_pixmaps()

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

        self.house_pet = HousePetWidget(self.state, parent=self)
        self.house_pet.raise_()

        self.desktop_pet.hide()

    def reload_bg_pixmaps(self):
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

        wp_id = self.state.selected_bg.get("wallpaper")
        if wp_id and wp_id in self.bg_pix["wallpaper"]:
            painter.drawPixmap(0, 0, self.bg_pix["wallpaper"][wp_id])
        else:
            if not self.default_bg.isNull():
                painter.drawPixmap(0, 0, self.default_bg)
            else:
                painter.fillRect(self.rect(), Qt.white)

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
            is_low = (state.mood <= 35) or (state.fun <= 20) or (state.energy <= 20) or (state.hunger <= 18)
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

        # ✅ 펫 상태 bar: fun / mood 분리
        self.fun_bar = QProgressBar()
        self.fun_bar.setRange(0, 100)
        self.fun_bar.setFormat("재미 %p%")

        self.mood_bar = QProgressBar()
        self.mood_bar.setRange(0, 100)
        self.mood_bar.setFormat("기분 %p%")

        self.hunger_bar = QProgressBar()
        self.hunger_bar.setRange(0, 100)
        self.hunger_bar.setFormat("배고픔 %p%")

        self.energy_bar = QProgressBar()
        self.energy_bar.setRange(0, 100)
        self.energy_bar.setFormat("에너지 %p%")

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
        layout.addWidget(self.fun_bar)
        layout.addWidget(self.mood_bar)
        layout.addWidget(self.hunger_bar)
        layout.addWidget(self.energy_bar)
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
        self.fun_bar.setValue(int(self.state.fun))
        self.mood_bar.setValue(int(self.state.mood))
        self.hunger_bar.setValue(int(self.state.hunger))

        # energy는 max_energy 기준으로 0~100으로 보이게
        ratio = (self.state.energy / max(1.0, self.state.max_energy)) * 100.0
        self.energy_bar.setValue(int(clamp(ratio, 0, 100)))

    def state_tick_1s(self):
        active_pet = self.get_active_pet()

        # 자연 감소
        self.state.hunger -= 1.0 * DECAY_MULT
        self.state.energy -= 0.6 * DECAY_MULT

        # 배고프거나 에너지 낮으면 mood 떨어짐
        if self.state.hunger < 25:
            self.state.mood -= 1.0 * DECAY_MULT
        if self.state.energy < 20:
            self.state.mood -= 1.0 * DECAY_MULT

        # 재미는 시간이 지나면 아주 조금 감소(심심함)
        self.state.fun -= 0.3 * DECAY_MULT

        # 회복
        if getattr(active_pet, "sleeping", False):
            self.state.energy += 1.2
            self.state.mood += 0.2
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

        if self.state.fun <= BORED_WARN_FUN:
            msg = random.choice(["심심해…", "놀아줘…", "찍… 뭐해?"])
            active_pet.say(msg, duration=2.2)
            self.add_log(who, msg)
            self.last_needy_talk_at = now
            return

        if self.state.mood <= 25:
            msg = random.choice(["기분이 좀…", "찍… 우울해…", "안아줘…"])
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
                "available_faces": active_pet.get_available_faces(),
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

        self.state.apply_delta({"hunger": +22, "fun": +1, "mood": +2, "energy": +1})
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
        self.state.apply_delta({"fun": +1, "mood": +8, "energy": 0, "hunger": -1})

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
        self.state.apply_delta({"fun": +10, "mood": +3, "energy": -3, "hunger": -2})

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

    if not FURNITURE_JSON_PATH.exists():
        print("⚠️ furniture.json이 없어! 폴더 스캔 폴백으로 실행 중:", FURNITURE_JSON_PATH)

    state = PetState()
    pet = PetWindow(state, app_icon=app_icon)
    panel = ControlPanel(state, pet, app_icon=app_icon)

    pet.show()
    panel.show()

    sys.exit(app.exec())