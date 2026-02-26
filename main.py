import sys
import random
import time

from pathlib import Path
from typing import Dict, Any, List, Optional

from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QSize, QEvent
from PySide6.QtGui import QPixmap, QPainter, QFont, QIcon, QTransform,QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QProgressBar, QLabel, QListWidget, QListWidgetItem, QSizePolicy,
    QTextEdit, QLineEdit
)

import os
import json
import urllib.request
import urllib.error


# =========================
# ✅ Groq Direct Settings
# =========================
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = "그롭 앱키"
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
APP_ICON_PATH = ASSET_DIR / "app.ico"  # ico 권장

HOUSE_BG_PATH = ASSET_DIR / "background" / "hamsterHouse.png"

HOUSE_WIN_W = 620  # 대충 600대
HOUSE_WIN_H = int(HOUSE_WIN_W * 864 / 1184)  # 원본비율 유지 (약 452)
HOUSE_SCALE_CHAR = 0.33  # 집 안에서는 더 작게 (원래 0.35였지)
HOUSE_SCALE_CHAR = 0.33   # 집 안 쥐 크기 (기존 0.22 * 1.5)
HOUSE_SCALE_BUBBLE = 0.15  # 집 안 말풍선 크기


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
}

EAT_SHAKE_DURATION = 0.8
EAT_SHAKE_STRENGTH = 3

DECAY_MULT = 1.0 / 9.0  # ✅ 허기/에너지 감소 더 느리게

SLEEP_TRIGGER_ENERGY = 15.0
SLEEP_DURATION_SEC = 60.0
SLEEP_RECOVER_ENERGY = 45.0

HUNGRY_WARN_HUNGER = 22.0
BORED_WARN_JOY = 12.0
NEEDY_TALK_COOLDOWN_SEC = 18.0

WANDER_INTERVAL_MS_RANGE = (3_000, 7_000)  # ✅ 더 자주 움직이게

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
        너의 유일한 출력 형식은 반드시 **JSON 오브젝트 하나**다.
        설명, 인사말, 코드블록, 마크다운, 주석, 여분 텍스트를 절대 출력하지 마라.
        JSON 형식이 조금이라도 깨지면 실패다.

        ────────────────────────
        [캐릭터 페르소나 - 절대 변경 불가]
        이름: 라이미(default)
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
        - 질문 가능하지만 짧게

        ────────────────────────
        [입력 데이터]
        사용자가 보내는 JSON에는 다음 키가 있다.

        event:
        - type: CHAT | FEED | PET | PLAY | AUTO
        - text: 사용자의 말 (빈 문자열 가능)

        state:
        - hunger: 0~100 (높을수록 배고픔)
        - energy: 0~100
        - mood: 0~100
        - joy: 0~100
        - last_face: 마지막으로 사용한 face 코드

        available_faces:
        - 사용할 수 있는 face 코드 배열 (문자열)

        ────────────────────────
        [출력 스키마 - 키 이름 변경 금지]
        {
        "reply": string,
        "face": string,
        "bubble_sec": number,
        "delta": {
            "joy": number,
            "mood": number,
            "energy": number,
            "hunger": number
        },
        "commands": [
            { "type":"SHAKE", "sec":number, "strength":number } |
            { "type":"JUMP", "strength":number } |
            { "type":"SET_MODE", "mode":"normal|walk|sleep|speak|eat", "sec":number }
        ]
        }

        ────────────────────────
        [필수 규칙]
        - reply는 반드시 존재해야 한다 (빈 문자열 금지)
        - reply는 1문장만 허용
        - face는 반드시 available_faces 안의 값만 사용
        - available_faces가 비어있다면 state.last_face 사용
        - bubble_sec 범위: 1.2 ~ 3.0
        - delta 값 범위: -10 ~ +10
        - commands는 최대 2개
        - commands가 없으면 빈 배열 []

        ────────────────────────
        [이벤트별 반응 가이드]

        1) CHAT
        - 사용자의 말에 감정적으로 반응
        - 설명 금지, 정보 제공 금지
        - 공감 / 애교 / 단순 반응 위주
        - joy 또는 mood 위주로 변화

        2) FEED
        - 먹는 걸 좋아함
        - hunger는 감소(-)
        - joy 또는 energy 소폭 증가
        - SET_MODE "eat" 우선 고려

        3) PET
        - 쓰다듬으면 매우 좋아함
        - joy/mood 증가
        - SHAKE 또는 JUMP 자주 사용

        4) PLAY
        - 즐거워하지만 에너지 소모
        - joy 증가, energy 감소
        - JUMP 자주 사용

        5) AUTO
        - 혼잣말
        - 짧고 일상적인 말
        - state 값에 따라 피곤/배고픔 표현

        ────────────────────────
        [감정 상태 판단 기준]

        - hunger >= 70 → 배고픔 언급 가능
        - energy <= 30 → 졸림 / 쉬고 싶음
        - mood <= 30 → 시무룩한 말투
        - joy >= 70 → 텐션 높은 말투

        ────────────────────────
        [절대 금지 사항]
        - JSON 밖 텍스트 출력
        - 여러 문장 사용
        - 설명, 분석, 조언
        - available_faces에 없는 face 사용
        - 스키마에 없는 키 추가
        - 캐릭터 설정 변경

        이 규칙을 어기면 출력은 즉시 폐기된다.
        """.strip()

    system = system.replace(
        "{PET_NAME}",
        payload.get("state", {}).get("pet_name", "라이미")
    )

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
        self.pet_name = "라이미"  # ✅ 기본 이름
        self.hunger = 60.0
        self.energy = 70.0
        self.mood = 70.0
        self.joy = 20.0
        self.last_face = "normal01"
        self.money = 0

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


class HouseWindow(QWidget):
    def __init__(self, state: PetState, desktop_pet: "PetWindow", icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state
        self.desktop_pet = desktop_pet

        self.setWindowTitle("집")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if icon:
            self.setWindowIcon(icon)

        # ✅ 창 크기 고정
        self.setFixedSize(HOUSE_WIN_W, HOUSE_WIN_H)

        # ✅ 배경 로드 (없으면 그냥 단색)
        self.bg = QPixmap(str(HOUSE_BG_PATH))
        if not self.bg.isNull():
            self.bg = self.bg.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

        # ✅ 집 안에서만 움직이는 펫 (작은 버전)
        self.house_pet = HousePetWidget(self.state, parent=self)
        self.house_pet.raise_()

        # 집 들어가면 바탕화면 펫 숨기기
        self.desktop_pet.hide()
    

    def closeEvent(self, e):
        # 집 창 닫히면 바탕화면 펫 다시 보이기
        try:
            self.desktop_pet.show()
            self.desktop_pet.raise_()
        except Exception:
            pass
        super().closeEvent(e)

    def paintEvent(self, e):
        painter = QPainter(self)
        if self.bg and not self.bg.isNull():
            painter.drawPixmap(0, 0, self.bg)
        else:
            painter.fillRect(self.rect(), Qt.white)


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


class ShopWindow(SimpleWindow):
    def __init__(self, state: PetState, icon: Optional[QIcon] = None):
        super().__init__("상점", icon=icon)
        self.state = state

        btn = QPushButton("간식 사기 (-300원, 허기 +10, 즐거움 +3)")
        btn.clicked.connect(self.buy_snack)
        self.layout().addWidget(btn)

        self.result = QLabel("")
        self.result.setObjectName("HintLabel")
        self.layout().addWidget(self.result)

    def buy_snack(self):
        if self.state.money < 300:
            self.result.setText("돈이 부족해…")
            return
        self.state.money -= 300
        self.state.hunger = clamp(self.state.hunger + 10)
        self.state.joy = clamp(self.state.joy + 3)
        self.result.setText("간식 샀다! (허기+10, 즐거움+3)")


# ✅ 이름 변경 창
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
# Pet Window
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
        manual_sad = ["normal03"]  # ✅ 슬픈얼굴
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

            # ✅ 클릭 && 드래그 아님 → 쓰다듬
            if not self.was_dragged:
                self.on_pet_clicked()

            e.accept()

    def on_pet_clicked(self):
    # 자는 중이면 약한 반응
        if self.sleeping:
            self.say("찍… (골골)…", 1.8)
            return

        # 쓰다듬 효과
        self.start_shake(sec=0.35, strength=2)

        msg = random.choice([
            "헤헤…",
            "찍찍… 좋아!",
            "쓰담쓰담…",
            "기분 좋아…",
        ])
        self.say(msg, 2.0)

        # 상태 변화 (ControlPanel.on_pet 과 동일)
        self.state.apply_delta({
            "joy": +6,
            "mood": +3,
            "energy": 0,
            "hunger": -0.5,
        })

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
            if self.vx < 0 and self.walk_frames_flipped:
                pix = self.walk_frames_flipped[self.frame_i]
            else:
                pix = self.walk_frames[self.frame_i]
        elif self.mode == "sleep" and self.sleep_frames:
            pix = self.sleep_frames[self.frame_i]
        elif self.mode == "speak" and self.speak_frames:
            pix = self.speak_frames[self.frame_i]
        elif self.mode == "eat" and self.eat_frames:
            pix = self.eat_frames[self.eat_static_i]
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
            bx = head_x - bubble_w // 2
            by = head_y - bubble_h - gap

            bx = max(0, min(self.width() - bubble_w, bx))
            by = max(0, by)

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

class HousePetWidget(QWidget):
    """
    집 창 내부에서만 움직이는 펫 위젯 (말풍선 포함)
    - 배경은 HouseWindow가 그림
    - 이 위젯은 펫만 그림/이동/말풍선 담당
    """
    def __init__(self, state: PetState, parent=None):
        super().__init__(parent)
        self.state = state

        # ✅ paintEvent가 먼저 불려도 안 죽게 기본값 선세팅
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

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        # ✅ 말풍선 준비
        bubble = QPixmap(str(BUBBLE_PATH))
        if not bubble.isNull():
            self.bubble = bubble.scaled(
                int(bubble.width() * HOUSE_SCALE_BUBBLE),
                int(bubble.height() * HOUSE_SCALE_BUBBLE),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        # ✅ 집 전용 스케일로 로드
        self.emotion_map = load_folder_pixmaps_as_map(ANIM_DIR / "emotion", HOUSE_SCALE_CHAR)
        if not self.emotion_map:
            raise FileNotFoundError("asset/animation/emotion 폴더에 png가 없어!")

        self.walk_frames = load_folder_pixmaps_as_list(ANIM_DIR / "walk", HOUSE_SCALE_CHAR)
        self.sleep_frames = load_folder_pixmaps_as_list(ANIM_DIR / "sleep", HOUSE_SCALE_CHAR)
        self.speak_frames = load_folder_pixmaps_as_list(ANIM_DIR / "speak", HOUSE_SCALE_CHAR)
        self.eat_frames = load_folder_pixmaps_as_list(ANIM_DIR / "eat", HOUSE_SCALE_CHAR)

        self.walk_frames_flipped = []
        if self.walk_frames:
            t = QTransform()
            t.scale(-1, 1)
            self.walk_frames_flipped = [fr.transformed(t, Qt.SmoothTransformation) for fr in self.walk_frames]

        # ✅ 크기 계산 (말풍선 + 캐릭터)
        any_pix = next(iter(self.emotion_map.values()))
        self.char_w = any_pix.width()
        self.char_h = any_pix.height()

        self.bubble_h = self.bubble.height() if self.bubble else int(60 * HOUSE_SCALE_CHAR)
        self.resize(self.char_w, self.char_h + self.bubble_h)
        self.char_y = self.bubble_h

        # ✅ 시작 얼굴
        keys = list(self.emotion_map.keys())
        self.current_face = self.state.last_face if self.state.last_face in keys else random.choice(keys)

        # ✅ 타이머 시작
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.advance_frame)
        self.anim_timer.start(ANIM_SPEED_MS.get("walk", 240))

        self.logic_timer = QTimer(self)
        self.logic_timer.timeout.connect(self.tick_logic)
        self.logic_timer.start(16)

        self.wander_timer = QTimer(self)
        self.wander_timer.timeout.connect(self.auto_wander)
        self.wander_timer.start(random.randint(1200, 2600))

        # ✅ 시작 위치(바닥 근처)
        self.reset_ground()
        self.move(random.randint(20, max(20, (self.parent().width() if self.parent() else 300) - self.width() - 20)), self.ground_y)

        # ✅ 첫 멘트
        self.say("찍! 집이다 🏠", duration=2.2)

    def say(self, text: str, duration: float = 2.2):
        self.say_text = text
        self.say_until = time.time() + float(duration)
        self.update()

    def reset_ground(self):
        if not self.parent():
            self.ground_y = 0
            return
        parent_h = self.parent().height()
        # 바닥: 부모 높이 - 내 높이 - 여백
        self.ground_y = max(0, parent_h - self.height() - 10)

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

    def start_shake(self, sec: float = 0.5, strength: int = 2):
        self.shake_until = time.time() + float(sec)
        self.shake_strength = max(0, int(strength))
        self.update()

    def auto_wander(self):
        self.wander_timer.start(random.randint(1200, 2600))
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
        self.update()

    def tick_logic(self):
        now = time.time()

        if now > self.mode_until and self.mode in ("walk", "sleep", "speak", "eat"):
            self.set_mode("normal", sec=99999)

        self.reset_ground()

        # ✅ 집 안에서만 좌우 이동 제한
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

        # 중력 + 바닥
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

            # 프레임 선택
            if self.mode == "walk" and self.walk_frames:
                if self.vx < 0 and self.walk_frames_flipped:
                    pix = self.walk_frames_flipped[self.frame_i]
                else:
                    pix = self.walk_frames[self.frame_i]
            elif self.mode == "sleep" and self.sleep_frames:
                pix = self.sleep_frames[self.frame_i]
            elif self.mode == "speak" and self.speak_frames:
                pix = self.speak_frames[self.frame_i]
            elif self.mode == "eat" and self.eat_frames:
                pix = self.eat_frames[0]
            else:
                pix = self.emotion_map.get(self.current_face) or next(iter(self.emotion_map.values()))

            # 흔들림
            dx = dy = 0
            if time.time() < self.shake_until and self.shake_strength > 0:
                dx = random.randint(-self.shake_strength, self.shake_strength)
                dy = random.randint(-self.shake_strength, self.shake_strength)

            # 캐릭터
            painter.drawPixmap(dx, dy + self.char_y, pix)

            # 말풍선 만료
            if self.say_text and time.time() > self.say_until:
                self.say_text = ""

            # 말풍선
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
# Apply AI result
# =========================
def apply_ai_result(state: PetState, pet: PetWindow, result: Dict[str, Any]):
    state.apply_delta(result.get("delta", {}))

    face = result.get("face")
    if face:
        is_low = (state.mood <= 35) or (state.joy <= 20) or (state.energy <= 20) or (state.hunger <= 18)
        if (not is_low) and (face in getattr(pet, "sad_faces", [])):
            if getattr(pet, "normal_faces", None):
                face = random.choice(pet.normal_faces)
        pet.set_face(face, hold_sec=FACE_HOLD_SEC)

    reply = result.get("reply", "")
    sec = float(result.get("bubble_sec", 2.2))
    if reply:
        pet.say(reply, duration=sec)

    for cmd in result.get("commands", []):
        ctype = cmd.get("type")
        if ctype == "SHAKE":
            pet.start_shake(sec=float(cmd.get("sec", 0.5)), strength=int(cmd.get("strength", 3)))
        elif ctype == "JUMP":
            pet.do_jump(int(cmd.get("strength", 12)))
        elif ctype == "SET_MODE":
            pet.set_mode(str(cmd.get("mode", "normal")), sec=float(cmd.get("sec", 1.5)))


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

        # ✅ 소지금/집/알바/상점 + 이름 변경
        self.money_win = MoneyWindow(self.state, icon=self.ico)
        self.home_win = None  # 필요할 때 만들거임
        self.job_win = JobWindow(self.state, icon=self.ico)
        self.shop_win = ShopWindow(self.state, icon=self.ico)
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

    def update_titles(self):
        # ✅ 이름 바꾸면 UI에 바로 반영되게
        self.setWindowTitle(f"{self.state.pet_name} - Chat Panel")

    # ✅ Enter=전송 / Shift+Enter=줄바꿈
    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False  # Shift+Enter = 줄바꿈
                self.on_send_chat()  # Enter = 전송
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
        self.state.hunger -= 1.0 * DECAY_MULT
        self.state.energy -= 0.6 * DECAY_MULT

        if self.state.hunger < 25:
            self.state.mood -= 1.0 * DECAY_MULT
        if self.state.energy < 20:
            self.state.mood -= 1.0 * DECAY_MULT

        if self.pet.sleeping:
            self.state.energy += 1.2
        elif self.pet.mode == "normal":
            self.state.energy += 0.2

        self.state.clamp_all()
        self.refresh()

        if (not self.pet.sleeping) and self.state.energy <= SLEEP_TRIGGER_ENERGY:
            self.pet.start_sleep_for_60s()

    def check_needs_and_talk(self):
        if self.pet.sleeping:
            return

        now = time.time()
        if now - self.last_needy_talk_at < NEEDY_TALK_COOLDOWN_SEC:
            return

        who = self.state.pet_name

        if self.state.hunger <= HUNGRY_WARN_HUNGER:
            msg = random.choice(["배고파… 밥…", "찍… 배고픈데…", "밥 생각나…"])
            self.pet.say(msg, duration=2.2)
            self.add_log(who, msg)
            self.last_needy_talk_at = now
            return

        if self.state.joy <= BORED_WARN_JOY:
            msg = random.choice(["심심해…", "놀아줘…", "찍… 뭐해?"])
            self.pet.say(msg, duration=2.2)
            self.add_log(who, msg)
            self.last_needy_talk_at = now
            return

    def open_money(self):
        self.money_win.refresh()
        self.money_win.show()
        self.money_win.raise_()
        self.money_win.activateWindow()

    def open_home(self):
        # 이미 열려있으면 앞으로
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
        self.shop_win.show()
        self.shop_win.raise_()
        self.shop_win.activateWindow()

    def open_name(self):
        # 현재 이름 갱신해서 보여주기
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
            payload = {
                "event": {"type": "CHAT", "text": text, "source": "chat"},
                "state": self.state.to_dict(),
                "available_faces": self.pet.get_available_faces(),
            }
            result = call_groq_chat(payload, timeout_sec=30.0)
            apply_ai_result(self.state, self.pet, result)

            reply = result.get("reply", "")
            if reply:
                self.add_log(self.state.pet_name, reply)

            self.refresh()
        finally:
            self.ai_busy = False

    def on_feed(self):
        who = self.state.pet_name

        if self.pet.sleeping:
            msg = "찍… 자는 중… (나중에…)"
            self.pet.say(msg, 2.0)
            self.add_log(who, msg)
            return

        self.pet.trigger_eat_visual()
        self.add_log("나", "🍚 밥줬다")

        self.state.apply_delta({"hunger": +22, "joy": +3, "mood": +2, "energy": +1})
        msg = random.choice(["냠냠! 맛있다!", "찍! 밥이다!", "너무 맛있어…"])
        self.pet.say(msg, 2.2)
        self.add_log(who, msg)
        self.refresh()

    def on_pet(self):
        who = self.state.pet_name

        if self.pet.sleeping:
            msg = "찍… (골골)…"
            self.pet.say(msg, 2.0)
            self.add_log(who, msg)
            return

        self.add_log("나", "🤍 쓰다듬었다")
        self.state.apply_delta({"joy": +8, "mood": +4, "energy": 0, "hunger": -1})

        self.pet.start_shake(sec=0.35, strength=2)
        msg = random.choice(["헤헤… 좋아…", "찍찍… 기분 좋아!", "쓰담쓰담 최고…"])
        self.pet.say(msg, 2.2)
        self.add_log(who, msg)
        self.refresh()

    def on_play(self):
        who = self.state.pet_name

        if self.pet.sleeping:
            msg = "찍… 지금은 졸려…"
            self.pet.say(msg, 2.0)
            self.add_log(who, msg)
            return

        self.add_log("나", "🎾 놀아줬다")
        self.state.apply_delta({"joy": +10, "mood": +3, "energy": -3, "hunger": -2})

        self.pet.do_jump(13)
        self.pet.set_mode("walk", sec=1.4)
        msg = random.choice(["놀자!!", "찍찍! 신난다!", "하하! 더 놀자!"])
        self.pet.say(msg, 2.2)
        self.add_log(who, msg)
        self.refresh()


# =========================
# Main
# =========================
# =========================
# Main
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # ✅ 앱 아이콘 먼저
    app_icon = QIcon(str(APP_ICON_PATH)) if APP_ICON_PATH.exists() else None
    if app_icon:
        app.setWindowIcon(app_icon)

    # ✅ 폰트는 QApplication 만든 다음에!
    # 파일명이 다를 수도 있으니 폴더에서 ttf를 찾아서 로드(안전)
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

    # ✅ QSS 적용은 폰트 로드 이후가 좋음(폰트가 QSS에 반영되게)
    load_qss(app)

    state = PetState()
    pet = PetWindow(state, app_icon=app_icon)
    panel = ControlPanel(state, pet, app_icon=app_icon)

    pet.show()
    panel.show()

    sys.exit(app.exec())