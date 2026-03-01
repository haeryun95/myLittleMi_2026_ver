"""
config.py - 전역 상수 및 경로 설정
"""
import sys
from pathlib import Path

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
app_icon_PATH = ASSET_DIR / "app.ico"

# 아이콘 디렉터리
app_icon_DIR = ASSET_DIR / "app_icon"

# 배경/가구
BG_DIR = ASSET_DIR / "background"
BG_DEFAULT_PATH = BG_DIR / "default.png"
FURNITURE_JSON_PATH = BG_DIR / "furniture.json"
HOUSE_BG_PATH = BG_DIR / "hamsterHouse.png"

# 알바/아이템
JOBS_JSON_PATH = ASSET_DIR / "jobs.json"
ITEMS_JSON_PATH = ASSET_DIR / "items.json"
SHOP_JSON_PATH = ASSET_DIR / "shop.json"

# =========================
# Groq Settings
# =========================
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = "앱키"  # TODO: 키 넣기
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_MAX_ATTEMPTS = 2
GROQ_RETRY_DELAY_SEC = 0.6

# =========================
# UI / Window Tunings
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
SLEEP_DURATION_SEC = 30.0
SLEEP_RECOVER_ENERGY = 45.0

HUNGRY_WARN_HUNGER = 22.0
BORED_WARN_FUN = 12.0
NEEDY_TALK_COOLDOWN_SEC = 18.0
WANDER_INTERVAL_MS_RANGE = (3_000, 7_000)

# =========================
# House Furniture / Layers
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
# Job Window
# =========================
SCRIPT_LINES_DEFAULT = 10
SCRIPT_LINES_RANGE = (8, 12)

STAT_LABELS = {
    "power": "힘",
    "fun": "흥미도",
    "cute": "귀여움",
}
