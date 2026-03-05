"""
utils/helpers.py - 공통 유틸리티 함수
"""
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication,QTextEdit


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def load_json_file(path: Path, fallback=None):
    try:
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def safe_read_json(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_qss(app: QApplication, qss_path: Path):
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

def trigger_pet_action_bubble(
    target_pet: Any, 
    chat_log: Optional[QTextEdit], 
    dialogues: List[str], 
    bubble_sec: float = 2.2
):
    """
    대상 펫 객체에 무작위 대사로 말풍선을 띄우는 유틸리티 함수.
    """
    if not target_pet or not dialogues:
        return

    msg = random.choice(dialogues)
    try:
        # 펫 위젯에 show_bubble 메서드가 존재한다고 가정
        if hasattr(target_pet, "show_bubble"):
            target_pet.show_bubble(msg, bubble_sec=bubble_sec)
        elif chat_log is not None:
            chat_log.append("[알림] 펫 객체에 'show_bubble(text, bubble_sec)' 메서드가 없습니다.")
    except Exception as ex:
        if chat_log is not None:
            chat_log.append(f"[오류] 말풍선 출력 실패: {ex}")
            LANG_DIR = Path("asset/lang")

_cache = {}

def load_lang(lang):
    if lang in _cache:
        return _cache[lang]

    path = LANG_DIR / f"{lang}.json"

    if not path.exists():
        path = LANG_DIR / "ko.json"

    data = json.loads(path.read_text(encoding="utf-8"))
    _cache[lang] = data
    return data


def t(state, key, fallback=""):
    lang = getattr(state, "lang", "ko")
    data = load_lang(lang)

    cur = data

    for k in key.split("."):
        if k not in cur:
            return fallback
        cur = cur[k]

    return cur