"""
windows/house_window.py - 집 창 + 집 안 펫 위젯

요구사항 반영:
1) sleep 중 쳇바퀴 탑승/스냅/드랍 불가
2) 드래그 시 drag 모션 확실 적용 + 그림자(더 아래)
3) 기분이 sad(슬픔)일 때만 울음/슬픔 표정 허용
4) 버튼을 테마 에셋 이미지로 시도 적용(없으면 기존 스타일 유지)
5) deco/bridge는 반투명 + 레이어 최상단
6) 가구상점/배치 창은 스타일 동일(개별 파일에서 동일 스타일 적용)
7) 먹기 모션: eat 폴더에서 랜덤 1장 고정 + shake (순환 금지)
8) 대화 시: speak 모션(2프레임 반복) + 살짝 점프(1회)
9) i18n: asset/lang/ko.json or en.json (state.lang 기반)
10) 레이어 순서:
    배경 -> (집/가구/flower) -> 쳇바퀴 -> (펫 위젯) -> deco/bridge(반투명)
11) 배치/가구상점 동시 오픈 방지(깜빡임 버그 대응: 서로 닫고 열기)
"""

import json
import random
import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QRect, QTimer, QPoint, QSize
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton, QWidget

from config import (
    ANIM_DIR,
    ANIM_SPEED_MS,
    BG_CATEGORIES,
    BG_DEFAULT_PATH,
    BUBBLE_PATH,
    EAT_SHAKE_DURATION,
    EAT_SHAKE_STRENGTH,
    FACE_HOLD_SEC,
    HOUSE_BUBBLE_PADDING,
    HOUSE_SCALE_BUBBLE,
    HOUSE_SCALE_CHAR,
    HOUSE_WIN_H,
    HOUSE_WIN_W,
    SLEEP_DURATION_SEC,
)

# ✅ ASSET_DIR이 없을 수도 있어서 방어
try:
    from config import ASSET_DIR  # type: ignore
except Exception:
    ASSET_DIR = Path("asset")

from state import PetState, clamp
from utils.image_loader import load_folder_pixmaps_as_map, load_folder_pixmaps_as_list, make_flipped_frames
from utils.json_utils import get_catalog, resolve_bg_path
from ui.placement_panel import PlacementPanel
from body import apply_ai_result

try:
    from groq_api import call_groq_chat
except Exception:
    call_groq_chat = None

from windows.furniture_shop_window import FurnitureShopWindow


WHEEL_SNAP_Y_OFFSET = 30  # ✅ 스냅 지점보다 30px 아래


# -----------------------
# i18n helpers
# -----------------------



def _guess_lang_from_state(state: PetState) -> str:
    print(state._lang)
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


def reload_language(self):
    self._lang = _load_lang_dict(_guess_lang_from_state(self.state))
    self.setWindowTitle(_t(self._lang, "buttons.home", "집"))
    self.placement_btn.setText(_t(self._lang, "ui.place", "배치"))
    self.furn_shop_btn.setText(_t(self._lang, "ui.furniture_shop", "가구상점"))
    

def _t(lang: Dict, path: str, fallback: str = ""):
    cur = lang
    for k in path.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return fallback
    return cur if isinstance(cur, str) else fallback


# -----------------------
# theme asset helpers
# -----------------------
def _resolve_ui_asset(state: PetState, filename: str) -> Optional[str]:
    """
    후보:
      asset/ui/{theme}/{filename}
      asset/ui/default/{filename}
      asset/ui/{filename}
    """
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


def _apply_themed_button(btn: QPushButton, state: PetState, base_name: str):
    """
    base_name 예: "button_90x36"
      - {base}.png
      - {base}_hover.png (없으면 normal)
      - {base}_pressed.png (없으면 normal)
    """
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


class HousePetWidget(QWidget):
    def __init__(self, state: PetState, parent=None):
        super().__init__(parent)
        self.state = state

        # i18n
        def L(self):
            return _load_lang_dict(_guess_lang_from_state(self.state))

        # drag
        self.dragging = False
        self.press_pos: Optional[QPoint] = None
        self.start_pos = QPoint(0, 0)
        self.was_dragged = False

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

        self.bubble: Optional[QPixmap] = None
        self.bubble_h = 0
        self.char_y = 0

        self.sleeping = False
        self.sleep_end_at = 0.0

        # wheel ride state
        self.on_wheel = False
        self.walk_in_place_until = 0.0
        self.wheel_anchor: Optional[QPoint] = None
        self._saved_walk_ms: Optional[int] = None

        # wheel walk fallback
        self._wheel_walk_last_at = 0.0
        self._wheel_walk_ms = 80

        # eat: random single frame
        self._eat_pix_fixed: Optional[QPixmap] = None

        # talk hop one-shot
        self._pending_talk_hop = False

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)

        # bubble image
        bubble = QPixmap(str(BUBBLE_PATH))
        if not bubble.isNull():
            self.bubble = bubble.scaled(
                int(bubble.width() * HOUSE_SCALE_BUBBLE),
                int(bubble.height() * HOUSE_SCALE_BUBBLE),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        # faces
        self.emotion_map = load_folder_pixmaps_as_map(ANIM_DIR / "emotion", HOUSE_SCALE_CHAR)
        if not self.emotion_map:
            raise FileNotFoundError("asset/animation/emotion 폴더에 png가 없어!")

        keys = list(self.emotion_map.keys())

        # ✅ sad/cry 자동 추출(하지만 mood sad일 때만 사용)
        auto_sad = [k for k in keys if any(t in k.lower() for t in ["sad", "cry", "tear", "depress", "down"])]
        manual_sad = [k for k in ["normal03"] if k in keys]  # 필요하면 여기에 추가
        self.sad_faces = sorted(list({*auto_sad, *manual_sad}))
        self.normal_faces = [k for k in keys if k not in self.sad_faces] or keys

        if self.state.last_face in keys:
            self.current_face = self.state.last_face
        else:
            self.current_face = random.choice(self.normal_faces)

        # anim frames
        self.walk_frames = load_folder_pixmaps_as_list(ANIM_DIR / "walk", HOUSE_SCALE_CHAR)
        self.sleep_frames = load_folder_pixmaps_as_list(ANIM_DIR / "sleep", HOUSE_SCALE_CHAR)
        self.speak_frames = load_folder_pixmaps_as_list(ANIM_DIR / "speak", HOUSE_SCALE_CHAR)
        self.eat_frames = load_folder_pixmaps_as_list(ANIM_DIR / "eat", HOUSE_SCALE_CHAR)

        # dragging frames (폴더명 draging 유지)
        self.drag_frames = load_folder_pixmaps_as_list(ANIM_DIR / "draging", HOUSE_SCALE_CHAR)
        self.drag_frames_flipped = make_flipped_frames(self.drag_frames) if self.drag_frames else []
        self.walk_frames_flipped = make_flipped_frames(self.walk_frames) if self.walk_frames else []
        self.speak_frames_flipped = make_flipped_frames(self.speak_frames) if self.speak_frames else []

        any_pix = next(iter(self.emotion_map.values()))
        self.char_w = any_pix.width()
        self.char_h = any_pix.height()
        self.bubble_h = self.bubble.height() if self.bubble else int(60 * HOUSE_SCALE_CHAR)

        self.resize(self.char_w, self.char_h + self.bubble_h)
        self.char_y = self.bubble_h

        # timers
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.advance_frame)
        self.anim_timer.start(ANIM_SPEED_MS.get("walk", 240))

        self.logic_timer = QTimer(self)
        self.logic_timer.timeout.connect(self.tick_logic)
        self.logic_timer.start(16)

        self.wander_timer = QTimer(self)
        self.wander_timer.timeout.connect(self.auto_wander)
        self.wander_timer.start(random.randint(1200, 2600))

        # init pos
        self.reset_ground()
        pw = self.parent().width() if self.parent() else 300
        self.move(random.randint(20, max(20, pw - self.width() - 20)), self.ground_y)
        self.say(_t(self.L(), "pet.enter_home", "찍! 집이다 🏠"), duration=2.2, use_speak=False)

        if getattr(self.state, "energy", 100) < 4:
            self.start_sleep_for_60s()

        self.show()

    # ----------------
    # helpers
    # ----------------
    def get_available_faces(self) -> List[str]:
        return list(self.emotion_map.keys())

    def _is_mood_sad(self) -> bool:
        mv = getattr(self.state, "mood", None)
        if isinstance(mv, str):
            return mv.lower() == "sad"
        if isinstance(mv, (int, float)):
            return float(mv) <= 25.0  # 프로젝트 기준에 맞춰 필요하면 튜닝
        ms = getattr(self.state, "mood_state", None)
        if isinstance(ms, str) and ms:
            return ms.lower() == "sad"
        return False

    def _ensure_not_sad_face(self):
        if not self._is_mood_sad() and self.current_face in self.sad_faces:
            self.current_face = random.choice(self.normal_faces)
            self.state.last_face = self.current_face

    def set_face(self, face_code: str, hold_sec: float = FACE_HOLD_SEC):
        if face_code in self.sad_faces and not self._is_mood_sad():
            return
        if face_code in self.emotion_map:
            self.current_face = face_code
            self.state.last_face = face_code
            self.update()

    def say(self, text: str, duration: float = 2.2, use_speak: bool = True):
        self.say_text = text
        self.say_until = time.time() + float(duration)

        if use_speak and not self.sleeping:
            now = time.time()
            on_wheel = (self.walk_in_place_until > 0.0 and now < self.walk_in_place_until)
            if not on_wheel and self.speak_frames:
                self.set_mode("speak", sec=min(1.2, float(duration)))
            self._pending_talk_hop = True

        self.update()

    def show_bubble(self, text: str, bubble_sec: float = 2.2):
        self.say(text, duration=bubble_sec, use_speak=True)

    def start_shake(self, sec: float = 0.5, strength: int = 2):
        self.shake_until = time.time() + float(sec)
        self.shake_strength = max(0, int(strength))
        self.update()

    def _do_small_hop_if_possible(self):
        if not self._pending_talk_hop:
            return
        if self.dragging or self.sleeping:
            self._pending_talk_hop = False
            return
        if abs(self.y() - self.ground_y) <= 2:
            self.vy = -7
        self._pending_talk_hop = False

    def set_mode(self, mode: str, sec: float = 1.5):
        if mode not in ("normal", "walk", "sleep", "speak", "eat", "drag"):
            mode = "normal"
        self.mode = mode
        self.frame_i = 0

        if mode in ANIM_SPEED_MS:
            self.anim_timer.start(ANIM_SPEED_MS[mode])
        else:
            self.anim_timer.start(90 if mode == "drag" else 120 if mode == "speak" else 999999)

        self.mode_until = time.time() + float(sec)
        self.update()

    def _set_fast_walk(self, enable: bool):
        base = ANIM_SPEED_MS.get("walk", 240)
        if enable:
            if self._saved_walk_ms is None:
                self._saved_walk_ms = base
            fast = max(60, int(base * 0.55))
            self.anim_timer.start(fast)
        else:
            if self._saved_walk_ms is not None:
                self.anim_timer.start(self._saved_walk_ms)
                self._saved_walk_ms = None

    def trigger_eat_visual(self):
        # ✅ eat: 랜덤 1장 고정 + shake (순환 금지)
        self._eat_pix_fixed = random.choice(self.eat_frames) if self.eat_frames else None
        self.set_mode("eat", sec=1.0)
        self.start_shake(sec=EAT_SHAKE_DURATION, strength=EAT_SHAKE_STRENGTH)

    def start_sleep_for_60s(self):
        if self.sleeping:
            return
        self.sleeping = True
        self.sleep_end_at = time.time() + SLEEP_DURATION_SEC
        self.set_mode("sleep", sec=SLEEP_DURATION_SEC + 0.2)

        sleeps = _t(self.L(), "interactions.sleep_pet", "")
        if isinstance(sleeps, list) and sleeps:
            self.say(str(random.choice(sleeps)), duration=2.0, use_speak=False)
        else:
            self.say("찍… 졸려…", duration=2.0, use_speak=False)

    def reset_ground(self):
        if not self.parent():
            self.ground_y = 0
            return
        parent_h = self.parent().height()
        self.ground_y = max(0, parent_h - self.height() - 10)

    def auto_wander(self):
        self.wander_timer.start(random.randint(1200, 2600))
        if self.sleeping or self.dragging or self.mode != "normal":
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
        # ✅ eat는 순환 금지
        elif self.mode == "drag" and self.drag_frames:
            self.frame_i = (self.frame_i + 1) % len(self.drag_frames)
        self.update()

    # ----------------
    # main logic
    # ----------------
    def tick_logic(self):
        now = time.time()

        self._ensure_not_sad_face()
        self.reset_ground()
        self._do_small_hop_if_possible()

        # sleep
        if self.sleeping:
            if now >= self.sleep_end_at or getattr(self.state, "energy", 100) >= 99.9:
                self.sleeping = False
                self.state.energy = clamp(getattr(self.state, "energy", 0), 0, 100)
                self.say(_t(self.L(), "pet.wake_up", "찍! 잘 잤다! 개운해!"), duration=2.2, use_speak=False)
                self.set_mode("normal", sec=99999)
            else:
                if self.mode != "sleep" and now > self.say_until:
                    self.set_mode("sleep", sec=max(0.1, self.sleep_end_at - now))
                self.state.energy = clamp(getattr(self.state, "energy", 0) + 0.15, 0, 100)
            return

        # wheel ride
        walk_in_place = (self.walk_in_place_until > 0.0 and now < self.walk_in_place_until)
        if walk_in_place:
            if self.wheel_anchor is None:
                self.wheel_anchor = self.pos()

            self.vy = 0
            self.move(self.wheel_anchor)

            if self.mode != "walk":
                self.mode = "walk"
                self.frame_i = 0

            if self.walk_frames:
                if self._wheel_walk_last_at <= 0:
                    self._wheel_walk_last_at = now
                if (now - self._wheel_walk_last_at) >= (self._wheel_walk_ms / 1000.0):
                    self.frame_i = (self.frame_i + 1) % len(self.walk_frames)
                    self._wheel_walk_last_at = now

            self._set_fast_walk(True)
            self.update()
            return

        # end wheel ride
        if self.walk_in_place_until > 0.0 and now >= self.walk_in_place_until:
            self.walk_in_place_until = 0.0
            self.wheel_anchor = None
            self._set_fast_walk(False)
            self._wheel_walk_last_at = 0.0

            parent = self.parent()
            if parent and hasattr(parent, "stop_wheel_spin"):
                parent.stop_wheel_spin()

            self.vy = -14
            self.set_mode("normal", sec=99999)
            self.say(_t(self.L(), "pet.wheel_end", "찍! 후우~"), 1.2, use_speak=False)

        # mode timeout
        if now > self.mode_until and self.mode in ("walk", "sleep", "speak", "eat"):
            self.set_mode("normal", sec=99999)

        # physics
        if not self.dragging:
            left = 0
            right = (self.parent().width() - self.width()) if self.parent() else 0
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
                if self.vy > 2:
                    self.start_shake(sec=0.18, strength=2)
                self.vy = 0

            self.move(int(x), int(y))

        self.update()

    # ----------------
    # input (drag/click)
    # ----------------
    def _is_over_blocked_ui(self, local_pos: QPoint) -> bool:
        parent = self.parent()
        if not parent:
            return False
        ppos = self.mapToParent(local_pos)
        for wname in ("placement_btn", "furn_shop_btn"):
            btn = getattr(parent, wname, None)
            if btn and btn.isVisible() and btn.geometry().contains(ppos):
                return True
        return False

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._is_over_blocked_ui(e.position().toPoint()):
                e.ignore()
                return

            self.dragging = True
            self.was_dragged = False
            self.press_pos = e.globalPosition().toPoint()
            self.start_pos = self.pos()

            self.setCursor(Qt.ClosedHandCursor)

            # ✅ 드래그 모션 확실히
            if not self.sleeping and self.drag_frames:
                self.set_mode("drag", sec=99999)

            e.accept()

    def mouseMoveEvent(self, e):
        if self.dragging:
            cur = e.globalPosition().toPoint()
            delta = cur - (self.press_pos or cur)

            if delta.manhattanLength() > 4:
                self.was_dragged = True

            # ✅ 드래그 방향으로 flip 반영
            if abs(delta.x()) >= 2:
                self.vx = -1 if delta.x() < 0 else 1

            target = self.start_pos + delta

            parent = self.parent()
            if parent:
                min_y = -self.bubble_h
                max_y = parent.height() - (self.height() // 3)
                min_x = -(self.width() // 2)
                max_x = parent.width() - (self.width() // 2)

                target.setX(max(min_x, min(max_x, target.x())))
                target.setY(max(min_y, min(max_y, target.y())))

                # ✅ 스냅 (sleep 중 제외)
                if hasattr(parent, "maybe_snap_to_wheel"):
                    snapped = parent.maybe_snap_to_wheel(target, self.size(), self)
                    if snapped is not None:
                        target = snapped
                        self.on_wheel = True
                    else:
                        self.on_wheel = False

            self.move(target)
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.OpenHandCursor)

            self.reset_ground()

            if self.sleeping:
                remain = max(0.1, self.sleep_end_at - time.time())
                self.set_mode("sleep", sec=remain)
            else:
                if self.mode == "drag":
                    self.set_mode("normal", sec=99999)

            if self.was_dragged:
                parent = self.parent()
                if parent and hasattr(parent, "handle_pet_dropped"):
                    parent.handle_pet_dropped(self)
            else:
                self.on_pet_clicked()

            e.accept()

    def on_pet_clicked(self):
        if self.sleeping:
            self.start_shake(sec=0.3, strength=2)
            self.say(_t(self.L(), "pet.sleep_click", "음냐... 졸려... 더 잘래 찍..."), 1.8, use_speak=False)
            remaining_sleep = max(0.1, self.sleep_end_at - time.time())
            self.set_mode("sleep", sec=remaining_sleep)
            return

        self.start_shake(sec=0.35, strength=2)
        msgs = _t(self.L(), "pet.click", [])
        msg = random.choice(msgs) if isinstance(msgs, list) and msgs else "찍!"
        self.say(msg, 2.0, use_speak=True)
        self.state.apply_delta({"fun": +2, "mood": +3, "energy": 0, "hunger": -0.3})

    def send_chat_from_panel(self, msg: str, chat_log):
        try:
            payload = {
                "event": "chat",
                "text": msg,
                "state": {
                    "pet_name": self.state.pet_name,
                    "hunger": float(self.state.hunger),
                    "energy": float(self.state.energy),
                    "mood": float(self.state.mood),
                    "fun": float(self.state.fun),
                    "money": int(self.state.money),
                    "last_face": self.state.last_face,
                },
                "available_faces": self.get_available_faces(),
            }
            if call_groq_chat:
                result = call_groq_chat(payload, timeout_sec=30.0)
            else:
                result = {
                    "reply": "찍… (집에서도 대화 가능!)",
                    "face": self.state.last_face,
                    "bubble_sec": 2.2,
                    "delta": {"fun": 1, "mood": 0, "energy": 0, "hunger": 0},
                    "commands": [],
                }

            apply_ai_result(self.state, self, result)

            reply = str(result.get("reply", "")).strip()
            bubble_sec = float(result.get("bubble_sec", 2.2) or 2.2)
            if reply:
                # ✅ 말풍선이 실제로 뜰 때 speak+hop
                self.show_bubble(reply, bubble_sec=bubble_sec)
                chat_log.append(f"{self.state.pet_name}: {reply}")
        except Exception as ex:
            chat_log.append(f"[오류] 집펫 AI 처리 실패: {ex}")

    # ----------------
    # render
    # ----------------
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self.mode == "drag" and self.drag_frames:
            pix = (
                self.drag_frames_flipped[self.frame_i]
                if self.vx < 0 and self.drag_frames_flipped
                else self.drag_frames[self.frame_i]
            )
        elif self.mode == "walk" and self.walk_frames:
            pix = (
                self.walk_frames_flipped[self.frame_i]
                if self.vx < 0 and self.walk_frames_flipped
                else self.walk_frames[self.frame_i]
            )
        elif self.mode == "sleep" and self.sleep_frames:
            pix = self.sleep_frames[self.frame_i]
        elif self.mode == "speak" and self.speak_frames:
            pix = (
                self.speak_frames_flipped[self.frame_i]
                if self.vx < 0 and self.speak_frames_flipped
                else self.speak_frames[self.frame_i]
            )
        elif self.mode == "eat":
            pix = self._eat_pix_fixed
            if pix is None and self.eat_frames:
                pix = random.choice(self.eat_frames)
                self._eat_pix_fixed = pix
        else:
            pix = self.emotion_map.get(self.current_face) or next(iter(self.emotion_map.values()))

        dx = dy = 0
        if time.time() < self.shake_until and self.shake_strength > 0:
            dx = random.randint(-self.shake_strength, self.shake_strength)
            dy = random.randint(-self.shake_strength, self.shake_strength)

        # ✅ drag shadow (더 아래)
        if self.mode == "drag" and pix and not pix.isNull():
            painter.save()
            painter.setOpacity(0.22)
            sw = int(pix.width() * 0.55)
            sh = max(6, int(pix.height() * 0.12))
            sx = (self.width() // 2) - (sw // 2) + dx
            sy = self.char_y + pix.height() + int(10 * HOUSE_SCALE_CHAR) + dy
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.black)
            painter.drawEllipse(sx, sy, sw, sh)
            painter.restore()

        if pix and not pix.isNull():
            painter.drawPixmap(dx, dy + self.char_y, pix)

        # bubble
        if self.say_text and time.time() > self.say_until:
            self.say_text = ""

        if self.say_text:
            # ✅ DirectWrite 오류 방지용: 안전 폰트만
            painter.setFont(QFont("Segoe UI", 10))

            bubble_w = self.bubble.width() if self.bubble else int(180 * HOUSE_SCALE_CHAR)
            bubble_h = self.bubble.height() if self.bubble else int(50 * HOUSE_SCALE_CHAR)

            head_x = self.width() // 2
            head_y = self.char_y + int(pix.height() * 0.4) if pix else self.char_y
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
                painter.drawRoundedRect(bubble_rect, 10, 10)
                painter.setOpacity(1.0)

            try:
                l, t, r, b = HOUSE_BUBBLE_PADDING
            except Exception:
                l, t, r, b = (10, 10, 10, 10)

            text_rect = bubble_rect.adjusted(l, t, -r, -b)
            painter.setPen(Qt.black)
            painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.say_text)


class HouseWindow(QWidget):
    def __init__(self, state: PetState, desktop_pet, app_icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state
        self.pet = desktop_pet
        self.app_icon = app_icon

        self._lang = _load_lang_dict(_guess_lang_from_state(state))

        self.setWindowTitle(_t(self.L(), "buttons.home", "집"))
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if app_icon:
            self.setWindowIcon(app_icon)

        self.setFixedSize(HOUSE_WIN_W, HOUSE_WIN_H)

        self.default_bg = QPixmap(str(BG_DEFAULT_PATH)) if BG_DEFAULT_PATH.exists() else QPixmap()
        if not self.default_bg.isNull():
            self.default_bg = self.default_bg.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        self.bg_pix: Dict[str, Dict[str, QPixmap]] = {cat: {} for cat in BG_CATEGORIES}
        self.reload_bg_pixmaps()

        # init order
        self.placement_panel: Optional[PlacementPanel] = None
        self.furniture_shop: Optional[FurnitureShopWindow] = None

        # wheel anim state
        self.wheel_spinning = False
        self.wheel_frame_i = 0
        self._wheel_spin_end_at = 0.0
        self._wheel_anim_cache: Dict[str, Dict] = {}

        self.wheel_timer = QTimer(self)
        self.wheel_timer.timeout.connect(self._tick_wheel_spin)
        self.wheel_timer.start(60)

        # buttons
        self.placement_btn = QPushButton(_t(self.L(), "ui.place", "배치"), self)
        self.placement_btn.setCursor(Qt.PointingHandCursor)
        self.placement_btn.clicked.connect(self.open_placement_panel)

        self.furn_shop_btn = QPushButton(_t(self.L(), "ui.furniture_shop", "가구상점"), self)
        self.furn_shop_btn.setCursor(Qt.PointingHandCursor)
        self.furn_shop_btn.clicked.connect(self.open_furniture_shop)

        # base style (fallback)
        base_ss = """
            QPushButton {
                background: rgba(255,255,255,178); border: 1px solid rgba(0,0,0,60);
                border-radius: 10px; padding: 6px 12px;
                font-weight: 900; min-height: 30px;
            }
            QPushButton:hover { background: rgba(255,255,255,210); }
        """
        self.placement_btn.setStyleSheet(base_ss)
        self.furn_shop_btn.setStyleSheet(base_ss)

        # try themed asset
        _apply_themed_button(self.placement_btn, self.state, "button_90x36")
        _apply_themed_button(self.furn_shop_btn, self.state, "button_90x36")

        self.placement_btn.adjustSize()
        self.furn_shop_btn.adjustSize()

        self._reposition_overlay_ui()

        # pet
        self.house_pet = HousePetWidget(self.state, parent=self)
        self.house_pet.raise_()
        self._raise_overlay_ui()

    # ----------------
    # overlay ui
    # ----------------
    def _raise_overlay_ui(self):
        self.placement_btn.raise_()
        self.furn_shop_btn.raise_()

        pp = getattr(self, "placement_panel", None)
        if pp:
            pp.raise_()
        fs = getattr(self, "furniture_shop", None)
        if fs:
            fs.raise_()

        # 펫은 위로, 버튼은 항상 최상단
        if getattr(self, "house_pet", None):
            self.house_pet.raise_()
            self.placement_btn.raise_()
            self.furn_shop_btn.raise_()

    def _reposition_overlay_ui(self):
        margin = 10
        self.placement_btn.move(self.width() - self.placement_btn.width() - margin, margin)
        self.furn_shop_btn.move(self.placement_btn.x() - self.furn_shop_btn.width() - 8, margin)
        self._raise_overlay_ui()

    # ----------------
    # lifecycle
    # ----------------
    def showEvent(self, e):
        try:
            self.pet.hide()
        except Exception:
            pass

        if getattr(self, "house_pet", None):
            self.house_pet.show()
            self.house_pet.raise_()

        self._raise_overlay_ui()
        super().showEvent(e)

    def closeEvent(self, e):
        try:
            self.pet.show()
            self.pet.raise_()
        except Exception:
            pass
        super().closeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition_overlay_ui()

        if not self.default_bg.isNull() and BG_DEFAULT_PATH.exists():
            self.default_bg = QPixmap(str(BG_DEFAULT_PATH)).scaled(
                self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )

        self._wheel_anim_cache.clear()
        self.reload_bg_pixmaps()
        self.update()

    # ----------------
    # open panels (동시 오픈 금지)
    # ----------------
    def open_furniture_shop(self):
        # 배치 열려있으면 닫고 열기
        if self.placement_panel and self.placement_panel.isVisible():
            self.placement_panel.close()
            self.placement_panel = None

        if self.furniture_shop and self.furniture_shop.isVisible():
            self.furniture_shop.raise_()
            self.furniture_shop.activateWindow()
            return

        self.furniture_shop = FurnitureShopWindow(
            self.state, app_icon=self.app_icon, on_purchased=self._on_layer_changed, parent=self
        )
        self.furniture_shop.show()
        self.furniture_shop.raise_()
        self.furniture_shop.activateWindow()
        self._raise_overlay_ui()

    def open_placement_panel(self):
        # 가구상점 열려있으면 닫고 열기
        if self.furniture_shop and self.furniture_shop.isVisible():
            self.furniture_shop.close()
            self.furniture_shop = None

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
        self._raise_overlay_ui()

    def _on_layer_changed(self):
        self._wheel_anim_cache.clear()
        self.update()

    # ----------------
    # bg loading
    # ----------------
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

    # ----------------
    # wheel helpers
    # ----------------
    def _selected_wheel_id(self) -> Optional[str]:
        wid = self.state.selected_bg.get("wheel")
        return wid if wid else None

    def _has_owned_selected_wheel(self) -> bool:
        wid = self._selected_wheel_id()
        if not wid:
            return False
        owned = self.state.owned_bg.get("wheel", set())
        if isinstance(owned, (list, tuple)):
            return wid in owned
        return wid in owned

    def _wheel_anim_dir_for(self, wheel_id: str) -> Optional[Path]:
        catalog = get_catalog()
        for it in catalog.get("wheel", []):
            if it.get("id") == wheel_id:
                rel = it.get("anim_dir")
                if not rel:
                    return None
                return (ASSET_DIR / str(rel)).resolve()
        return None

    # ----------------
    # wheel zone / snap
    # ----------------
    def _wheel_zone_rect(self) -> QRect:
        w = self.width()
        h = self.height()
        cx = int(w * 0.40)
        cy = int(h * 0.39)
        size = int(min(w, h) * 0.50)
        return QRect(cx - size // 2, cy - size // 2, size, size)

    def _infer_frame_mode(self, pm: QPixmap) -> str:
        if pm.isNull():
            return "full"
        if pm.width() >= int(self.width() * 0.85) and pm.height() >= int(self.height() * 0.85):
            return "full"
        return "zone"

    def _get_wheel_anim_frames(self, wheel_id: str) -> Dict:
        if not wheel_id:
            return {"frames": [], "mode": "full"}

        cache = self._wheel_anim_cache.get(wheel_id)
        if cache and cache.get("size") == self.size() and cache.get("frames"):
            return {"frames": cache["frames"], "mode": cache.get("mode", "full")}

        anim_dir = self._wheel_anim_dir_for(wheel_id)
        if not anim_dir or not anim_dir.exists():
            self._wheel_anim_cache[wheel_id] = {"size": self.size(), "frames": [], "mode": "full"}
            return {"frames": [], "mode": "full"}

        raw = load_folder_pixmaps_as_list(anim_dir, 1.0)

        mode = "full"
        for pm in raw:
            if pm and not pm.isNull():
                mode = self._infer_frame_mode(pm)
                break

        frames: List[QPixmap] = []
        if mode == "full":
            for pm in raw:
                if pm and not pm.isNull():
                    frames.append(pm.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        else:
            zone = self._wheel_zone_rect()
            for pm in raw:
                if pm and not pm.isNull():
                    frames.append(pm.scaled(zone.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self._wheel_anim_cache[wheel_id] = {"size": self.size(), "frames": frames, "mode": mode}
        return {"frames": frames, "mode": mode}

    def maybe_snap_to_wheel(self, pet_top_left: QPoint, pet_size: QSize, pet_widget: Optional[HousePetWidget] = None) -> Optional[QPoint]:
        if not self._has_owned_selected_wheel():
            return None
        if pet_widget is not None and getattr(pet_widget, "sleeping", False):
            return None

        wheel_id = self._selected_wheel_id()
        if not wheel_id or wheel_id not in self.bg_pix.get("wheel", {}):
            return None

        zone = self._wheel_zone_rect()

        px = pet_top_left.x() + (pet_size.width() // 2)
        py = pet_top_left.y() + pet_size.height()

        tx = zone.center().x()
        ty = zone.bottom()

        dist = abs(px - tx) + abs(py - ty)
        threshold = int(min(self.width(), self.height()) * 0.26)

        if dist <= threshold:
            snapped_x = tx - (pet_size.width() // 2)
            snapped_y = (ty - pet_size.height()) + WHEEL_SNAP_Y_OFFSET
            return QPoint(snapped_x, snapped_y)

        return None

    def handle_pet_dropped(self, pet_widget: HousePetWidget):
        if getattr(pet_widget, "sleeping", False):
            return
        if not self._has_owned_selected_wheel():
            return

        wheel_id = self._selected_wheel_id()
        if not wheel_id:
            return

        anim = self._get_wheel_anim_frames(wheel_id)
        if not anim["frames"]:
            return

        zone = self._wheel_zone_rect()
        px = pet_widget.x() + (pet_widget.width() // 2)
        py = pet_widget.y() + pet_widget.height()
        target = QPoint(zone.center().x(), zone.bottom())
        dist = abs(px - target.x()) + abs(py - target.y())

        if pet_widget.on_wheel or dist <= int(min(self.width(), self.height()) * 0.28):
            snapped = self.maybe_snap_to_wheel(pet_widget.pos(), pet_widget.size(), pet_widget)
            if snapped is not None:
                pet_widget.move(snapped)
            self.start_wheel_spin(pet_widget)

    # ----------------
    # wheel spin control
    # ----------------
    def start_wheel_spin(self, pet_widget: HousePetWidget):
        if getattr(pet_widget, "sleeping", False):
            return

        wheel_id = self._selected_wheel_id()
        if not wheel_id or not self._has_owned_selected_wheel():
            return

        anim = self._get_wheel_anim_frames(wheel_id)
        if not anim["frames"]:
            return

        self.wheel_spinning = True
        self.wheel_frame_i = 0

        duration = random.uniform(5.0, 10.0)
        self._wheel_spin_end_at = time.time() + duration

        pet_widget.walk_in_place_until = time.time() + duration
        pet_widget.vx = random.choice([-2, -1, 1, 2])
        pet_widget.wheel_anchor = pet_widget.pos()
        pet_widget.vy = 0
        pet_widget._wheel_walk_last_at = 0.0

        pet_widget.set_mode("walk", sec=duration + 0.2)
        self.say(_t(self.L(), "pet.wheel_start", "찍! 쳇바퀴다!"), 1.6, use_speak=False)

        self.update()

    def stop_wheel_spin(self):
        self.wheel_spinning = False
        self._wheel_spin_end_at = 0.0
        self.update()

    def _tick_wheel_spin(self):
        if not self.wheel_spinning:
            return
        if self._wheel_spin_end_at and time.time() >= self._wheel_spin_end_at:
            self.stop_wheel_spin()
            return

        wheel_id = self._selected_wheel_id()
        anim = self._get_wheel_anim_frames(wheel_id) if wheel_id else {"frames": [], "mode": "full"}
        frames = anim["frames"]
        if frames:
            self.wheel_frame_i = (self.wheel_frame_i + 1) % len(frames)
        self.update()

    # ----------------
    # render
    # ----------------
    def paintEvent(self, e):
        painter = QPainter(self)

        # 1) background/wallpaper
        wp_id = self.state.selected_bg.get("wallpaper")
        if wp_id and wp_id in self.bg_pix.get("wallpaper", {}):
            painter.drawPixmap(0, 0, self.bg_pix["wallpaper"][wp_id])
        else:
            if not self.default_bg.isNull():
                painter.drawPixmap(0, 0, self.default_bg)
            else:
                painter.fillRect(self.rect(), Qt.white)

        # 2) house & flower (wheel 아래)
        for cat in ["house", "flower"]:
            sel = self.state.selected_bg.get(cat)
            if sel and sel in self.bg_pix.get(cat, {}):
                painter.drawPixmap(0, 0, self.bg_pix[cat][sel])

        # 3) wheel (pet 아래)
        wheel_id = self.state.selected_bg.get("wheel")
        if wheel_id and wheel_id in self.bg_pix.get("wheel", {}):
            if self._has_owned_selected_wheel() and self.wheel_spinning:
                anim = self._get_wheel_anim_frames(wheel_id)
                frames = anim["frames"]
                mode = anim["mode"]
                if frames:
                    frame = frames[self.wheel_frame_i]
                    if mode == "full":
                        painter.drawPixmap(0, 0, frame)
                    else:
                        zone = self._wheel_zone_rect()
                        x = zone.x() + (zone.width() - frame.width()) // 2
                        y = zone.y() + (zone.height() - frame.height()) // 2
                        painter.drawPixmap(x, y, frame)
                else:
                    painter.drawPixmap(0, 0, self.bg_pix["wheel"][wheel_id])
            else:
                painter.drawPixmap(0, 0, self.bg_pix["wheel"][wheel_id])

        # 4) deco/bridge top (semi-transparent)
        for cat in ["deco", "bridge"]:
            if cat in self.bg_pix:
                sel = self.state.selected_bg.get(cat)
                if sel and sel in self.bg_pix.get(cat, {}):
                    painter.save()
                    painter.setOpacity(0.78)
                    painter.drawPixmap(0, 0, self.bg_pix[cat][sel])
                    painter.restore()

        self._raise_overlay_ui()