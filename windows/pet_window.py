"""
windows/pet_window.py - 데스크탑 위에 떠다니는 펫 창
"""

import random
import time
import json
from typing import List, Optional, Any, Dict, Tuple
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QRect, QTimer
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QWidget

from config import (
    ANIM_DIR, ANIM_SPEED_MS, BUBBLE_PATH,
    EAT_SHAKE_DURATION, EAT_SHAKE_STRENGTH, FACE_HOLD_SEC,
    NORMAL_RANDOM_INTERVAL, SCALE_BUBBLE, SCALE_CHAR,
    SLEEP_DURATION_SEC, WANDER_INTERVAL_MS_RANGE,
)
from state import PetState, clamp
from utils.image_loader import load_folder_pixmaps_as_map, load_folder_pixmaps_as_list, make_flipped_frames


# -----------------------------
# helpers
# -----------------------------
def _transform_pixmap_centered(
    pix: QPixmap,
    rotate_deg: float = 0.0,
    flip_x: bool = False,
    flip_y: bool = False,
) -> QPixmap:
    """pix를 중심 기준으로 회전/반전한 새 QPixmap 반환."""
    if pix is None or pix.isNull():
        return pix

    w, h = pix.width(), pix.height()
    t = QTransform()
    t.translate(w / 2, h / 2)

    if rotate_deg:
        t.rotate(rotate_deg)  # +는 반시계

    if flip_x or flip_y:
        t.scale(-1 if flip_x else 1, -1 if flip_y else 1)

    t.translate(-w / 2, -h / 2)
    return pix.transformed(t, Qt.SmoothTransformation)


def _safe_read_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _deep_get(d: Dict[str, Any], keypath: str, default=None):
    cur: Any = d
    for k in keypath.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


class PetWindow(QWidget):
    # -----------------------------
    # tuning constants
    # -----------------------------
    EDGE_MARGIN_LEFT = -50
    EDGE_MARGIN_RIGHT = -50
    EDGE_MARGIN_TOP = -50
    EDGE_MARGIN_BOTTOM = 0

    # climb 때는 별도 stick margin 사용
    CLIMB_STICK_MARGIN_LEFT = 0
    CLIMB_STICK_MARGIN_RIGHT = -100   # ✅ 오른쪽 벽만 더 바짝 붙이고 싶을 때 이 값 조절
    CLIMB_STICK_MARGIN_TOP = 0
    CLIMB_STICK_MARGIN_BOTTOM = 0

    EDGE_TRIGGER_PAD = 0
    AUTO_CLIMB_EDGE_RANGE = 100
    CLIMB_COOLDOWN_SEC = 0.35

    # ✅ drop 착지 위치를 현재 x 근처로 제한
    DROP_LANDING_JITTER_X = 55

    def __init__(self, state: PetState, app_icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state

        self.press_pos: Optional[QPoint] = None
        self.was_dragged = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if app_icon:
            self.setWindowIcon(app_icon)

        self.current_action_pixmap: Optional[QPixmap] = None

        # i18n
        self.lang_code = self._detect_lang_code()
        self.lang = self._load_lang(self.lang_code)

        # --- faces ---
        self.emotion_map = load_folder_pixmaps_as_map(ANIM_DIR / "emotion", SCALE_CHAR)
        if not self.emotion_map:
            raise FileNotFoundError("asset/animation/emotion 폴더에 png가 없어!")

        keys = list(self.emotion_map.keys())
        auto_sad = [k for k in keys if any(t in k.lower() for t in ["sad", "cry", "tear", "depress", "down"])]
        manual_sad = ["normal03"]
        self.sad_faces = sorted(list({*auto_sad, *[k for k in manual_sad if k in keys]}))
        self.normal_faces = [k for k in keys if k not in self.sad_faces]

        # --- animations ---
        self.walk_frames = load_folder_pixmaps_as_list(ANIM_DIR / "walk", SCALE_CHAR)
        self.sleep_frames = load_folder_pixmaps_as_list(ANIM_DIR / "sleep", SCALE_CHAR)
        self.speak_frames = load_folder_pixmaps_as_list(ANIM_DIR / "speak", SCALE_CHAR)
        self.eat_frames = load_folder_pixmaps_as_list(ANIM_DIR / "eat", SCALE_CHAR)
        self.sit_frames = load_folder_pixmaps_as_list(ANIM_DIR / "sit", SCALE_CHAR)
        self.drag_frames = load_folder_pixmaps_as_list(ANIM_DIR / "dragging", SCALE_CHAR)

        self.dance_frames = load_folder_pixmaps_as_list(ANIM_DIR / "dance", SCALE_CHAR)
        self.snooze_frames = load_folder_pixmaps_as_list(ANIM_DIR / "snooze", SCALE_CHAR)

        # climb
        self.climb_frames = load_folder_pixmaps_as_list(ANIM_DIR / "climb", SCALE_CHAR)
        self.pending_eat_after_drop = False

        # flipped caches
        self.walk_frames_flipped = make_flipped_frames(self.walk_frames) if self.walk_frames else []
        self.sit_frames_flipped = make_flipped_frames(self.sit_frames) if self.sit_frames else []
        self.drag_frames_flipped = make_flipped_frames(self.drag_frames) if self.drag_frames else []
        self.dance_frames_flipped = make_flipped_frames(self.dance_frames) if self.dance_frames else []

        # climb variants
        self.climb_frames_right = self.climb_frames[:] if self.climb_frames else []
        self.climb_frames_left = make_flipped_frames(self.climb_frames) if self.climb_frames else []
        self.climb_frames_top = [
            _transform_pixmap_centered(p, rotate_deg=270, flip_x=False, flip_y=False)
            for p in self.climb_frames
        ] if self.climb_frames else []

        # --- bubble ---
        bubble = QPixmap(str(BUBBLE_PATH))
        if bubble.isNull():
            self.bubble = None
        else:
            self.bubble = bubble.scaled(
                int(bubble.width() * SCALE_BUBBLE),
                int(bubble.height() * SCALE_BUBBLE),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )

        any_pix = next(iter(self.emotion_map.values()))
        self.char_w = any_pix.width()
        self.char_h = any_pix.height()

        self.bubble_h = self.bubble.height() if self.bubble else 45
        self.resize(self.char_w, self.char_h + self.bubble_h)

        self.screen_rect = QApplication.primaryScreen().availableGeometry()

        # 초기 위치(바닥)
        left, top, right, bottom = self._screen_edges_exclusive()
        min_x = self._left_target()
        max_x = self._max_x()

        if max_x < min_x:
            max_x = min_x

        start_x = random.randint(int(min_x), int(max_x))
        start_y = bottom - self.EDGE_MARGIN_BOTTOM - self._sprite_h_total()
        self.move(int(start_x), int(start_y))

        # drag
        self.dragging = False
        self.drag_offset = QPoint(0, 0)
        self.setCursor(Qt.OpenHandCursor)

        # bubble text
        self.say_text = ""
        self.say_until = 0.0

        # mode/state
        self.mode = "normal"
        self.frame_i = 0
        self.mode_until = time.time() + 99999
        self.current_face = getattr(self.state, "last_face", None) if getattr(self.state, "last_face", None) in self.emotion_map else random.choice(self.normal_faces or keys)
        self.next_normal_change = time.time() + NORMAL_RANDOM_INTERVAL
        self.face_until = 0.0

        # shake
        self.shake_until = 0.0
        self.shake_strength = 0

        # movement
        self.vx = random.choice([-2, -1, 1, 2])
        self.facing_left = False
        self.vy = 0
        self.gravity = 1

        # sleep
        self.sleeping = False
        self.sleep_end_at = 0.0

        # dance facing
        self.dance_facing_left = False

        # climb
        self.is_climbing = False
        self.climb_surface = ""        # 'left' | 'right' | 'top'
        self.climb_dir = 1             # left/right: +1 down, -1 up / top: +1 right, -1 left
        self.climb_phase = "hold"      # 'hold' | 'move'
        self.climb_phase_until = 0.0
        self.climb_total_end_at = 0.0
        self.climb_hold_min = 2.0
        self.climb_hold_max = 4.0
        self.climb_move_min = 0.8
        self.climb_move_max = 2.2
        self.climb_step_px = 20
        self.climb_cooldown_until = 0.0

        # drop
        self.is_dropping = False
        self.drop_target_x = 0

        # random talks
        self.random_dialogues: List[str] = []
        self._load_dialogues()

        # timers
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

    # -----------------------------
    # i18n
    # -----------------------------
    def _detect_lang_code(self) -> str:
        code = None
        try:
            code = getattr(self.state, "lang", None)
        except Exception:
            code = None

        if not code:
            try:
                settings = getattr(self.state, "settings", None)
                if isinstance(settings, dict):
                    code = settings.get("lang")
            except Exception:
                code = None

        code = (code or "ko").lower()
        if code not in ("ko", "en"):
            code = "ko"
        return code

    def _load_lang(self, code: str) -> Dict[str, Any]:
        base = Path(__file__).resolve().parents[1] / "asset" / "lang"
        data = _safe_read_json(base / f"{code}.json")
        if not data:
            data = _safe_read_json(base / "ko.json")
        return data or {}

    def t(self, keypath: str, default: Any = "") -> Any:
        v = _deep_get(self.lang, keypath, None)
        return default if v is None else v

    def t_choice(self, keypath: str, default_list: List[str]) -> str:
        v = self.t(keypath, None)
        if isinstance(v, list) and v:
            return random.choice(v)
        return random.choice(default_list)

    # -----------------------------
    # faces
    # -----------------------------
    def get_available_faces(self) -> List[str]:
        return list(self.emotion_map.keys())

    def set_face(self, face_code: str, hold_sec: float = FACE_HOLD_SEC):
        if face_code in self.emotion_map:
            self.current_face = face_code
            try:
                self.state.last_face = face_code
            except Exception:
                pass
            self.face_until = time.time() + hold_sec
            self.update()

    # -----------------------------
    # bubble API
    # -----------------------------
    def say(self, text: str, duration: float = 2.2):
        self.say_text = text
        self.say_until = time.time() + duration
        self.update()

    def show_bubble(self, text: str, bubble_sec: float = 2.2):
        self.say(text, duration=bubble_sec)

    # -----------------------------
    # shake / jump
    # -----------------------------
    def start_shake(self, sec: float = 0.6, strength: int = 4):
        self.shake_until = time.time() + sec
        self.shake_strength = max(1, int(strength))
        self.update()

    def do_jump(self, strength: int = 12):
        """바닥에 있을 때만 점프."""
        left, top, right, bottom = self._screen_edges_exclusive()
        floor_y = bottom - self.EDGE_MARGIN_BOTTOM - self._sprite_h_total()
        if abs(self.y() - floor_y) <= 2:
            self.vy = -abs(int(strength))

    # -----------------------------
    # dynamic char_y / sprite height
    # -----------------------------
    def _is_top_climb(self) -> bool:
        return self.is_climbing and self.mode == "climb" and self.climb_surface == "top"

    def _current_char_y(self) -> int:
        return 0 if self._is_top_climb() else self.bubble_h

    def _sprite_h_total(self) -> int:
        return self.height()

    # -----------------------------
    # geometry helpers
    # -----------------------------
    def _screen_edges_exclusive(self) -> Tuple[int, int, int, int]:
        s = self.screen_rect
        left = s.left()
        top = s.top()
        right = s.left() + s.width()
        bottom = s.top() + s.height()
        return left, top, right, bottom

    def _left_target(self) -> int:
        left, top, right, bottom = self._screen_edges_exclusive()
        return left + self.EDGE_MARGIN_LEFT

    def _right_target(self) -> int:
        left, top, right, bottom = self._screen_edges_exclusive()
        return right - self.EDGE_MARGIN_RIGHT

    def _top_target(self) -> int:
        left, top, right, bottom = self._screen_edges_exclusive()
        return top + self.EDGE_MARGIN_TOP

    def _max_x(self) -> int:
        return self._right_target() - self.char_w

    # 스프라이트 기준 좌표
    def _sprite_left(self) -> int:
        return self.x()

    def _sprite_right(self) -> int:
        return self.x() + self.char_w

    def _sprite_top(self) -> int:
        return self.y() + self._current_char_y()

    def _sprite_bottom(self) -> int:
        return self.y() + self._current_char_y() + self.char_h

    def _clamp_xy_with_custom_margin(
        self,
        x: int,
        y: int,
        left_margin: Optional[int] = None,
        right_margin: Optional[int] = None,
        top_margin: Optional[int] = None,
        bottom_margin: Optional[int] = None,
    ) -> Tuple[int, int]:
        left, top, right, bottom = self._screen_edges_exclusive()

        lm = self.EDGE_MARGIN_LEFT if left_margin is None else left_margin
        rm = self.EDGE_MARGIN_RIGHT if right_margin is None else right_margin
        tm = self.EDGE_MARGIN_TOP if top_margin is None else top_margin
        bm = self.EDGE_MARGIN_BOTTOM if bottom_margin is None else bottom_margin

        char_y = self._current_char_y()

        min_x = left + lm
        max_x = right - rm - self.char_w

        min_y = top + tm - char_y
        max_y = bottom - bm - (char_y + self.char_h)

        x = max(min_x, min(max_x, x))
        y = max(min_y, min(max_y, y))
        return x, y

    def _snap_to_surface(self, surface: str):
        """climb 중엔 방향별 stick margin으로 밀착."""
        left, top, right, bottom = self._screen_edges_exclusive()
        char_y = self._current_char_y()

        if self.is_climbing:
            lm = self.CLIMB_STICK_MARGIN_LEFT
            rm = self.CLIMB_STICK_MARGIN_RIGHT
            tm = self.CLIMB_STICK_MARGIN_TOP
            bm = self.CLIMB_STICK_MARGIN_BOTTOM
            left_target = left + lm
            right_target = right - rm
            top_target = top + tm
        else:
            lm = self.EDGE_MARGIN_LEFT
            rm = self.EDGE_MARGIN_RIGHT
            tm = self.EDGE_MARGIN_TOP
            bm = self.EDGE_MARGIN_BOTTOM
            left_target = self._left_target()
            right_target = self._right_target()
            top_target = self._top_target()

        x, y = self.x(), self.y()

        if surface == "left":
            x = left_target
        elif surface == "right":
            x = right_target - self.char_w
        elif surface == "top":
            y = top_target - char_y

        x, y = self._clamp_xy_with_custom_margin(int(x), int(y), lm, rm, tm, bm)
        self.move(int(x), int(y))

    def _pick_nearest_climb_surface(self) -> str:
        """가장 가까운 면 선택. 동점이면 top보다 left/right 우선."""
        dist_left = abs(self._sprite_left() - self._left_target())
        dist_right = abs(self._sprite_right() - self._right_target())
        dist_top = abs(self._sprite_top() - self._top_target())

        best = min(dist_left, dist_right, dist_top)
        candidates = []
        if dist_left == best:
            candidates.append("left")
        if dist_right == best:
            candidates.append("right")
        if dist_top == best:
            candidates.append("top")

        if "top" in candidates and ("left" in candidates or "right" in candidates):
            candidates = [c for c in candidates if c != "top"]

        return random.choice(candidates) if candidates else "right"

    def _is_within_auto_climb_range(self) -> bool:
        """자동 climb은 가장자리 100px 이내일 때만."""
        dist_left = abs(self._sprite_left() - self._left_target())
        dist_right = abs(self._sprite_right() - self._right_target())
        dist_top = abs(self._sprite_top() - self._top_target())
        return min(dist_left, dist_right, dist_top) <= self.AUTO_CLIMB_EDGE_RANGE

    def _is_on_edge_for_drag_trigger(self) -> bool:
        """드래그 후 클라임 트리거."""
        pad = self.EDGE_TRIGGER_PAD

        at_left = self._sprite_left() <= self._left_target() + pad
        at_right = self._sprite_right() >= self._right_target() - pad
        at_top = self._sprite_top() <= self._top_target() + pad

        return at_left or at_right or at_top

    # -----------------------------
    # dialogues / sleep / eat
    # -----------------------------
    def _load_dialogues(self):
        try:
            path = Path(__file__).resolve().parents[1] / "asset" / "data" / "dialogue.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.random_dialogues = data.get("random_talks", [])
        except Exception:
            pass

    def trigger_eat_visual(self):
        if self.is_climbing:
            self.pending_eat_after_drop = True
            self._stop_climb()
            self._start_drop()
            return

        if self.is_dropping:
            self.pending_eat_after_drop = True
            return

        self.set_mode("eat", sec=1.5)
        self.start_shake(sec=EAT_SHAKE_DURATION, strength=EAT_SHAKE_STRENGTH)

    def start_sleep_for_60s(self):
        if self.sleeping:
            return
        self.sleeping = True
        self.sleep_end_at = time.time() + SLEEP_DURATION_SEC
        self.set_mode("sleep", sec=SLEEP_DURATION_SEC + 0.2)
        self.say(self.t_choice("interactions.sleep_pet", ["음… 피곤해…", "Zzz…"]), duration=2.4)

    # -----------------------------
    # mode
    # -----------------------------
    def set_mode(self, mode: str, sec: float = 1.5):
        if mode not in ("normal", "walk", "sleep", "speak", "eat", "drag", "sit", "dance", "snooze", "climb"):
            mode = "normal"

        self.mode = mode
        self.frame_i = 0
        self.mode_until = time.time() + float(sec)

        if mode == "dance":
            self.dance_facing_left = random.choice([True, False])

        if mode == "eat" and self.eat_frames:
            self.current_action_pixmap = random.choice(self.eat_frames)
        else:
            self.current_action_pixmap = None

        if mode in ANIM_SPEED_MS:
            self.anim_timer.start(ANIM_SPEED_MS[mode])
        elif mode == "climb":
            pass
        elif mode in ("sit", "dance"):
            self.anim_timer.start(150)
            if mode == "dance":
                self.state.apply_delta({"fun": random.uniform(1, 5)})
        elif mode == "snooze":
            self.anim_timer.start(400)
            self.state.apply_delta({"energy": random.uniform(1, 3)})
        elif mode == "drag":
            self.anim_timer.start(90)
        else:
            self.anim_timer.start(999999)

        self.update()

    # -----------------------------
    # climb state machine
    # -----------------------------
    def _schedule_next_climb_phase(self, now: float):
        if self.climb_phase == "hold":
            self.climb_phase_until = now + random.uniform(self.climb_hold_min, self.climb_hold_max)
            self.anim_timer.stop()
        else:
            self.climb_phase_until = now + random.uniform(self.climb_move_min, self.climb_move_max)
            self.anim_timer.start(random.randint(90, 170))

    def _start_climb(self, surface: Optional[str] = None):
        now = time.time()
        if now < self.climb_cooldown_until:
            return
        if self.dragging or self.sleeping or self.is_climbing or self.is_dropping:
            return
        if not self.climb_frames:
            return

        self.is_climbing = True
        self.climb_surface = surface or self._pick_nearest_climb_surface()

        self.climb_total_end_at = now + random.uniform(8.0, 18.0)
        self.climb_dir = random.choice([-1, 1])
        self.vx = 0
        self.vy = 0

        self._snap_to_surface(self.climb_surface)

        self.climb_phase = "hold"
        self._schedule_next_climb_phase(now)
        self.set_mode("climb", sec=99999)

    def _stop_climb(self):
        if not self.is_climbing:
            return
        self.is_climbing = False
        self.climb_phase = "hold"
        self.climb_cooldown_until = time.time() + self.CLIMB_COOLDOWN_SEC
        self.anim_timer.start(200)
        if self.mode == "climb":
            self.set_mode("normal", sec=99999)

    def _climb_step(self):
        """move 단계에서만: 프레임 1회마다 20px 이동."""
        if not self.is_climbing or self.climb_phase != "move":
            return

        left, top, right, bottom = self._screen_edges_exclusive()
        lm = self.CLIMB_STICK_MARGIN_LEFT
        rm = self.CLIMB_STICK_MARGIN_RIGHT
        tm = self.CLIMB_STICK_MARGIN_TOP
        bm = self.CLIMB_STICK_MARGIN_BOTTOM

        x, y = self.x(), self.y()
        step = self.climb_dir * self.climb_step_px
        char_y = self._current_char_y()

        if self.climb_surface in ("left", "right"):
            y += step
            min_y = top + tm - char_y
            max_y = bottom - bm - (char_y + self.char_h)
            if y <= min_y:
                y = min_y
                self.climb_dir *= -1
            elif y >= max_y:
                y = max_y
                self.climb_dir *= -1

        elif self.climb_surface == "top":
            x += step
            min_x = left + lm
            max_x = right - rm - self.char_w
            if x <= min_x:
                x = min_x
                self.climb_dir *= -1
            elif x >= max_x:
                x = max_x
                self.climb_dir *= -1
            y = top + tm - char_y

        if self.climb_surface == "left":
            x = left + lm
        elif self.climb_surface == "right":
            x = right - rm - self.char_w
        elif self.climb_surface == "top":
            y = top + tm - char_y

        x, y = self._clamp_xy_with_custom_margin(int(x), int(y), lm, rm, tm, bm)
        self.move(x, y)

    # -----------------------------
    # drop
    # -----------------------------
    def _pick_drop_landing_x_near_current(self) -> int:
        min_x = self._left_target()
        max_x = self._max_x()

        if max_x < min_x:
            max_x = min_x

        candidate = self.x() + random.randint(-self.DROP_LANDING_JITTER_X, self.DROP_LANDING_JITTER_X)
        return int(max(min_x, min(max_x, candidate)))

    def _start_drop(self):
        self.is_dropping = True
        self.drop_target_x = self._pick_drop_landing_x_near_current()
        self.vy = -9
        self.set_mode("normal", sec=99999)

    # -----------------------------
    # wander
    # -----------------------------
    def auto_wander(self):
        self.wander_timer.start(random.randint(*WANDER_INTERVAL_MS_RANGE))

        if self.dragging or self.sleeping or self.is_climbing or self.is_dropping:
            return
        if self.mode in ("eat", "sleep", "drag", "climb"):
            return

        now = time.time()

        if now >= self.climb_cooldown_until:
            if self._is_within_auto_climb_range() and random.random() < 0.04:
                self._start_climb(None)
                return

        r = random.random()
        if r < 0.10:
            self.set_mode("dance", sec=random.uniform(2.0, 5.0))
        elif r < 0.20:
            self.set_mode("snooze", sec=random.uniform(2.0, 5.0))
        elif r < 0.35:
            self.facing_left = random.choice([True, False])
            self.set_mode("sit", sec=random.uniform(2.0, 4.0))
        elif r < 0.75:
            self.vx = random.choice([-3, -2, -1, 1, 2, 3])
            self.set_mode("walk", sec=random.uniform(1.5, 3.5))
        else:
            self.set_mode("normal", sec=random.uniform(1.0, 2.0))

    # -----------------------------
    # mouse events
    # -----------------------------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return

        if self.is_climbing:
            self._stop_climb()
        if self.is_dropping:
            self.is_dropping = False
            self.vy = 0
            self.climb_cooldown_until = time.time() + self.CLIMB_COOLDOWN_SEC

        self.dragging = True
        self.was_dragged = False
        self.press_pos = e.globalPosition().toPoint()
        self.drag_offset = self.press_pos - self.frameGeometry().topLeft()
        self.setCursor(Qt.ClosedHandCursor)

        if not self.sleeping and self.drag_frames:
            self.set_mode("drag", sec=99999)

        e.accept()

    def mouseMoveEvent(self, e):
        if not self.dragging:
            return

        current_pos = e.globalPosition().toPoint()
        if self.press_pos and (current_pos - self.press_pos).manhattanLength() > 4:
            self.was_dragged = True

        target = current_pos - self.drag_offset
        x, y = self._clamp_xy_with_custom_margin(target.x(), target.y())
        self.move(x, y)
        e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return

        self.dragging = False
        self.setCursor(Qt.OpenHandCursor)

        if self.mode == "drag":
            self.set_mode("normal", sec=99999)

        if self.was_dragged and (not self.sleeping) and (not self.is_climbing) and (not self.is_dropping):
            if self._is_on_edge_for_drag_trigger():
                self._start_climb(self._pick_nearest_climb_surface())

        if not self.was_dragged:
            self.on_pet_clicked()

        e.accept()

    def on_pet_clicked(self):
        self.start_shake(sec=0.35, strength=3)
        msg = random.choice(["헤헤…", "찍찍… 좋아!", "쓰담쓰담…", "기분 좋아…"])
        self.say(msg, 2.0)
        self.state.apply_delta({"fun": +3, "mood": +6, "energy": 0, "hunger": -0.5})

    # -----------------------------
    # frame advance
    # -----------------------------
    def advance_frame(self):
        if self.mode == "climb" and self.is_climbing:
            if self.climb_phase != "move":
                return
            self._climb_step()

        frames = {
            "walk": self.walk_frames,
            "sleep": self.sleep_frames,
            "speak": self.speak_frames,
            "drag": self.drag_frames,
            "sit": self.sit_frames,
            "dance": self.dance_frames,
            "snooze": self.snooze_frames,
            "climb": self.climb_frames,
        }.get(self.mode)

        if frames:
            self.frame_i = (self.frame_i + 1) % len(frames)

        self.update()

    # -----------------------------
    # main logic tick
    # -----------------------------
    def tick_logic(self):
        now = time.time()

        if self.sleeping:
            if now >= self.sleep_end_at or getattr(self.state, "energy", 0) >= 99.9:
                self.sleeping = False
                self.state.energy = clamp(self.state.energy, 0, 100)
                self.state.mood = clamp(self.state.mood + 5)
                self.say(self.t("ui.sys_ready", "[System] Raimi is ready."), 2.0)
                self.set_mode("normal", 99999)
            else:
                self.state.energy = clamp(self.state.energy + 0.05, 0, 100)
            self.update()
            return

        if self.mode == "normal" and now > self.face_until and now >= self.next_normal_change:
            mood = getattr(self.state, "mood", 50)
            if mood < 30:
                pool = self.sad_faces or self.normal_faces
            elif mood > 70:
                pool = [k for k in self.emotion_map if "happy" in k.lower()] + self.normal_faces
            else:
                pool = self.normal_faces
            if pool:
                self.current_face = random.choice(pool)
            self.next_normal_change = now + NORMAL_RANDOM_INTERVAL

        if self.mode == "normal" and (not self.dragging) and now > self.say_until:
            if random.random() < 0.0005 and self.random_dialogues:
                self.say(random.choice(self.random_dialogues), 3.0)
                self.set_mode("speak", sec=3.0)

        if self.dragging:
            self.update()
            return

        left, top, right, bottom = self._screen_edges_exclusive()
        x, y = self.x(), self.y()

        # drop
        if self.is_dropping:
            dx = self.drop_target_x - x
            if abs(dx) > 2:
                x += int(dx * 0.15)
            else:
                x = self.drop_target_x

            self.vy += self.gravity
            y += self.vy

            floor_y = bottom - self.EDGE_MARGIN_BOTTOM - self._sprite_h_total()
            if y >= floor_y:
                y = floor_y
                self.vy = 0
                self.is_dropping = False
                self.set_mode("normal", sec=99999)
                self.climb_cooldown_until = time.time() + self.CLIMB_COOLDOWN_SEC

                if self.pending_eat_after_drop:
                    self.pending_eat_after_drop = False
                    self.set_mode("eat", sec=1.5)
                    self.start_shake(sec=EAT_SHAKE_DURATION, strength=EAT_SHAKE_STRENGTH)

            x, y = self._clamp_xy_with_custom_margin(int(x), int(y))
            self.move(x, y)
            self.update()
            return

        # climb
        if self.is_climbing:
            self._snap_to_surface(self.climb_surface)

            if now >= self.climb_total_end_at:
                self._stop_climb()
                self._start_drop()
                self.update()
                return

            if now >= self.climb_phase_until:
                self.climb_phase = "move" if self.climb_phase == "hold" else "hold"
                self._schedule_next_climb_phase(now)

            self.update()
            return

        if now > self.mode_until and self.mode in ("walk", "sleep", "speak", "eat", "sit", "dance", "snooze"):
            self.set_mode("normal", 99999)

        if self.mode == "walk":
            x += self.vx

        self.vy += self.gravity
        y += self.vy

        floor_y = bottom - self.EDGE_MARGIN_BOTTOM - self._sprite_h_total()
        if y >= floor_y:
            y = floor_y
            self.vy = 0

        x, y = self._clamp_xy_with_custom_margin(int(x), int(y))
        self.move(x, y)
        self.update()

    # -----------------------------
    # render
    # -----------------------------
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        try:
            now = time.time()
            pix = None

            if self.mode == "drag" and self.drag_frames:
                frames = self.drag_frames_flipped if self.facing_left else self.drag_frames
                pix = frames[self.frame_i % len(frames)]

            elif self.mode == "climb" and self.climb_frames:
                idx = self.frame_i % len(self.climb_frames)
                if self.climb_surface == "right":
                    pix = self.climb_frames_right[idx]
                elif self.climb_surface == "left":
                    pix = self.climb_frames_left[idx]
                elif self.climb_surface == "top":
                    pix = self.climb_frames_top[idx]
                else:
                    pix = self.climb_frames_right[idx]

            elif self.mode == "dance" and self.dance_frames:
                frames = self.dance_frames_flipped if self.dance_facing_left else self.dance_frames
                pix = frames[self.frame_i % len(frames)] if frames else None

            elif self.mode == "snooze" and self.snooze_frames:
                pix = self.snooze_frames[self.frame_i % len(self.snooze_frames)] if self.snooze_frames else None

            elif self.mode == "eat" and self.current_action_pixmap:
                pix = self.current_action_pixmap

            elif self.mode == "speak" and self.speak_frames:
                pix = self.speak_frames[self.frame_i % len(self.speak_frames)] if self.speak_frames else None

            elif self.mode == "sit" and self.sit_frames:
                frames = self.sit_frames_flipped if self.facing_left else self.sit_frames
                pix = frames[self.frame_i % len(frames)] if frames else None

            elif self.mode == "walk" and self.walk_frames:
                frames = self.walk_frames_flipped if self.vx < 0 else self.walk_frames
                pix = frames[self.frame_i % len(frames)] if frames else None

            elif self.mode == "sleep" and self.sleep_frames:
                pix = self.sleep_frames[self.frame_i % len(self.sleep_frames)] if self.sleep_frames else None

            else:
                mood = getattr(self.state, "mood", 50)
                target_key = "happy" if mood > 70 else "sad" if mood < 30 else "normal"
                matches = [k for k in self.emotion_map.keys() if target_key in k.lower()]
                face_key = matches[0] if matches else self.current_face
                pix = self.emotion_map.get(face_key) or next(iter(self.emotion_map.values()))

            if not pix:
                return

            dx = dy = 0
            if now < self.shake_until and self.shake_strength > 0:
                dx = random.randint(-self.shake_strength, self.shake_strength)
                dy = random.randint(-self.shake_strength, self.shake_strength)

            char_y = self._current_char_y()
            painter.drawPixmap(dx, dy + char_y, pix)

            if self.say_text and now < self.say_until:
                font = QFont("Galmuri11", 10)
                font.setBold(True)
                painter.setFont(font)

                is_top = self._is_top_climb()
                char_y = self._current_char_y()

                bubble_pix = self.bubble
                if self.bubble and is_top:
                    bubble_pix = _transform_pixmap_centered(self.bubble, rotate_deg=-180)

                if self.bubble:
                    bw = bubble_pix.width()
                    bh = bubble_pix.height()
                else:
                    bw = 120
                    bh = 45

                # 기본은 가운데
                bx = (self.width() - bw) // 2

                if is_top:
                    # 천장에서는 아래
                    by = (char_y + self.char_h) + dy - 100

                elif self.mode == "climb" and self.climb_surface == "right":
                    # ✅ 오른쪽 벽 climb: 말풍선을 펫의 왼쪽으로
                    bx = dx - bw + 40
                    by = (char_y - bh) + dy + 60

                elif self.mode == "climb" and self.climb_surface == "left":
                    # ✅ 왼쪽 벽 climb: 말풍선을 펫의 오른쪽으로
                    bx = self.char_w + dx 
                    by = (char_y - bh) + dy + 60

                else:
                    # 평소: 위
                    by = (char_y - bh) + dy + 60

                bx = max(0, min(bx, self.width() - bw))
                by = max(0, min(by, self.height() - bh))
                bubble_rect = QRect(int(bx), int(by), bw, bh)

                if self.bubble:
                    painter.drawPixmap(bx + dx, by, bubble_pix)
                else:
                    painter.setOpacity(0.9)
                    painter.setBrush(Qt.white)
                    painter.setPen(Qt.NoPen)
                    painter.drawRoundedRect(bubble_rect, 10, 10)
                    painter.setOpacity(1.0)

                painter.setPen(Qt.black)
                painter.drawText(
                    bubble_rect.adjusted(10, 5, -10, -10),
                    Qt.AlignCenter | Qt.TextWordWrap,
                    self.say_text
                )
        finally:
            painter.end()