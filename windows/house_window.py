"""
windows/house_window.py - 집 창 + 집 안 펫 위젯
- showEvent: 데스크탑 펫 숨김(확실)
- closeEvent: 데스크탑 펫 복구
- 배치 옆 '가구상점' 버튼
- (B안) wheel 애니: furniture.json의 wheel.anim_dir 폴더 프레임 재생
- 쳇바퀴 탑승: 소지(owned) + 배치(선택 selected) 상태에서만 가능
- ✅ 수면 중에는 쳇바퀴 탑승 불가(스냅/드랍/자동탑승 모두 차단)
- 드래그 중 근처면 스냅(하단 중앙) + 스냅 위치에서 30px 아래에 펫 고정
- 드롭 시 5~10초: 쳇바퀴 애니 + 펫 제자리(빠른 walk) 고정 달리기
- 종료 시: 점프하듯 위로 튀고 중력으로 떨어져 바닥 착지
- 드래깅 애니 + 그림자
- 버튼 아래에 펫이 있어도 버튼 클릭이 펫으로 새지 않도록 방지(raise + hit-test)
- ✅ 배치/가구상점 동시 오픈 금지(깜빡임 방지)
- ✅ 레이어: 배경 → (house/flower) → wheel → pet(widget) → deco(overlay widget)
"""
from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QRect, QTimer, QPoint, QSize
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton, QWidget

from config import (
    ANIM_DIR, ANIM_SPEED_MS, BG_CATEGORIES, BG_DEFAULT_PATH,
    BUBBLE_PATH, EAT_SHAKE_DURATION, EAT_SHAKE_STRENGTH, FACE_HOLD_SEC,
    HOUSE_BUBBLE_PADDING, HOUSE_SCALE_BUBBLE, HOUSE_SCALE_CHAR,
    HOUSE_WIN_H, HOUSE_WIN_W, SLEEP_DURATION_SEC,
)

try:
    from config import ASSET_DIR  # type: ignore
except Exception:
    ASSET_DIR = Path("asset")

from state import PetState, clamp
from utils.image_loader import (
    load_folder_pixmaps_as_map,
    load_folder_pixmaps_as_list,
    make_flipped_frames,
)
from utils.json_utils import get_catalog, resolve_bg_path
from ui.placement_panel import PlacementPanel
from body import apply_ai_result

try:
    from groq_api import call_groq_chat
except Exception:
    call_groq_chat = None

from windows.furniture_shop_window import FurnitureShopWindow


WHEEL_SNAP_Y_OFFSET = 30


class DecoOverlay(QWidget):
    """
    펫 위에 'deco(브릿지 포함)'를 그리기 위한 오버레이.
    ✅ TransparentForMouseEvents로 펫 드래그/클릭을 방해하지 않게 함.
    """
    def __init__(self, parent: QWidget, get_pixmaps_callable):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._get = get_pixmaps_callable
        self.resize(parent.size())
        self.show()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.parent():
            self.resize(self.parent().size())

    def paintEvent(self, e):
        painter = QPainter(self)
        data = self._get()  # {"deco": QPixmap or None}
        pm = data.get("deco")
        if pm and not pm.isNull():
            painter.drawPixmap(0, 0, pm)


class HousePetWidget(QWidget):
    def __init__(self, state: PetState, parent=None):
        super().__init__(parent)
        self.state = state

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

        # “무조건 달리기 프레임 보장” 수동 프레임 진행
        self._wheel_walk_last_at = 0.0
        self._wheel_walk_ms = 80

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)

        # bubble
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
        self.current_face = self.state.last_face if self.state.last_face in keys else random.choice(keys)

        # anim frames
        self.walk_frames = load_folder_pixmaps_as_list(ANIM_DIR / "walk", HOUSE_SCALE_CHAR)
        self.sleep_frames = load_folder_pixmaps_as_list(ANIM_DIR / "sleep", HOUSE_SCALE_CHAR)
        self.speak_frames = load_folder_pixmaps_as_list(ANIM_DIR / "speak", HOUSE_SCALE_CHAR)
        self.eat_frames = load_folder_pixmaps_as_list(ANIM_DIR / "eat", HOUSE_SCALE_CHAR)

        # ✅ dance 있으면 로드(없어도 정상)
        self.dance_frames = load_folder_pixmaps_as_list(ANIM_DIR / "dance", HOUSE_SCALE_CHAR)

        # dragging frames (폴더명 draging 유지)
        self.drag_frames = load_folder_pixmaps_as_list(ANIM_DIR / "draging", HOUSE_SCALE_CHAR)
        self.drag_frames_flipped = make_flipped_frames(self.drag_frames) if self.drag_frames else []
        self.walk_frames_flipped = make_flipped_frames(self.walk_frames) if self.walk_frames else []
        self.dance_frames_flipped = make_flipped_frames(self.dance_frames) if self.dance_frames else []

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
        self.say("찍! 집이다 🏠", duration=2.2)

        if getattr(self.state, "energy", 0) < 4:
            self.start_sleep_for_60s()

        self.show()

    # ----------------
    # helpers
    # ----------------
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

    def show_bubble(self, text: str, bubble_sec: float = 2.2):
        self.say(text, duration=bubble_sec)

    def start_shake(self, sec: float = 0.5, strength: int = 2):
        self.shake_until = time.time() + float(sec)
        self.shake_strength = max(0, int(strength))
        self.update()

    def set_mode(self, mode: str, sec: float = 1.5):
        if mode not in ("normal", "walk", "sleep", "speak", "eat", "drag", "dance"):
            mode = "normal"
        self.mode = mode
        self.frame_i = 0

        if mode in ANIM_SPEED_MS:
            self.anim_timer.start(ANIM_SPEED_MS[mode])
        else:
            self.anim_timer.start(90 if mode == "drag" else 999999)

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
        if self.sleeping or self.dragging:
            return
        if self.mode != "normal":
            return

        parent = self.parent()
        # ✅ 자동 쳇바퀴 탑승(가끔)
        if parent and hasattr(parent, "try_auto_wheel_ride"):
            if parent.try_auto_wheel_ride(self):
                return

        # 가끔 춤(dance) - 폴더 있으면
        if self.dance_frames and random.random() < 0.10:
            self.set_mode("dance", sec=random.uniform(1.2, 2.2))
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
        elif self.mode == "drag" and self.drag_frames:
            self.frame_i = (self.frame_i + 1) % len(self.drag_frames)
        elif self.mode == "dance" and self.dance_frames:
            self.frame_i = (self.frame_i + 1) % len(self.dance_frames)
        self.update()

    # ----------------
    # main logic
    # ----------------
    def tick_logic(self):
        now = time.time()

        # sleep logic
        if self.sleeping:
            if now >= self.sleep_end_at or getattr(self.state, "energy", 0) >= 99.9:
                self.sleeping = False
                self.state.energy = clamp(self.state.energy, 0, 100)
                self.say("찍! 잘 잤다! 개운해!", duration=2.2)
                self.set_mode("normal", sec=99999)
            else:
                if self.mode != "sleep" and now > self.say_until:
                    self.set_mode("sleep", sec=max(0.1, self.sleep_end_at - now))
                self.state.energy = clamp(self.state.energy + 0.15, 0, 100)
            return

        # ✅ 쳇바퀴 탑승 여부
        walk_in_place = (self.walk_in_place_until > 0.0 and now < self.walk_in_place_until)

        # ✅ 탑승 중: 좌표 강제 고정 + 빠른 walk 반복 (중력/바닥로직 실행 금지)
        if walk_in_place:
            if self.wheel_anchor is None:
                self.wheel_anchor = self.pos()

            self.vy = 0
            self.move(self.wheel_anchor)

            if self.mode != "walk":
                self.mode = "walk"
                self.frame_i = 0

            # ✅ 타이머가 밀려도 “무조건” 달리는 모션이 나오도록 수동 프레임 진행
            if self.walk_frames:
                if self._wheel_walk_last_at <= 0:
                    self._wheel_walk_last_at = now
                if (now - self._wheel_walk_last_at) >= (self._wheel_walk_ms / 1000.0):
                    self.frame_i = (self.frame_i + 1) % len(self.walk_frames)
                    self._wheel_walk_last_at = now

            self._set_fast_walk(True)
            self.update()
            return

        # ✅ 탑승 끝나는 순간: 점프하듯 떨어지기
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
            self.say("찍! 후우~", 1.2)

        # mode timeout
        if now > self.mode_until and self.mode in ("walk", "sleep", "speak", "eat", "dance"):
            self.set_mode("normal", sec=99999)

        self.reset_ground()

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
            if not self.sleeping and self.drag_frames:
                self.set_mode("drag", sec=99999)
            e.accept()

    def mouseMoveEvent(self, e):
        if self.dragging:
            cur = e.globalPosition().toPoint()
            delta = cur - (self.press_pos or cur)

            if delta.manhattanLength() > 4:
                self.was_dragged = True

            target = self.start_pos + delta

            parent = self.parent()
            if parent:
                min_y = -self.bubble_h
                max_y = parent.height() - (self.height() // 3)
                min_x = -(self.width() // 2)
                max_x = parent.width() - (self.width() // 2)

                target.setX(max(min_x, min(max_x, target.x())))
                target.setY(max(min_y, min(max_y, target.y())))

                # ✅ 쳇바퀴 스냅(소지+배치 + 수면아님)
                if hasattr(parent, "maybe_snap_to_wheel"):
                    snapped = parent.maybe_snap_to_wheel(target, self.size(), self.sleeping)
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
                    parent.handle_pet_dropped(self, self.sleeping)
            else:
                self.on_pet_clicked()

            e.accept()

    def on_pet_clicked(self):
        if self.sleeping:
            self.start_shake(sec=0.3, strength=2)
            self.say("음냐... 졸려... 더 잘래 찍...", 1.8)
            remaining_sleep = max(0.1, self.sleep_end_at - time.time())
            self.set_mode("sleep", sec=remaining_sleep)
            return

        self.start_shake(sec=0.35, strength=2)
        msg = random.choice(["집이 좋아…", "찍찍!", "여기서 놀자!", "헤헤…"])
        self.say(msg, 2.0)
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
            if reply:
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
            pix = self.speak_frames[self.frame_i]
        elif self.mode == "eat" and self.eat_frames:
            pix = self.eat_frames[self.frame_i % len(self.eat_frames)]
        elif self.mode == "dance" and self.dance_frames:
            pix = (
                self.dance_frames_flipped[self.frame_i]
                if self.vx < 0 and self.dance_frames_flipped
                else self.dance_frames[self.frame_i]
            )
        else:
            pix = self.emotion_map.get(self.current_face) or next(iter(self.emotion_map.values()))

        dx = dy = 0
        if time.time() < self.shake_until and self.shake_strength > 0:
            dx = random.randint(-self.shake_strength, self.shake_strength)
            dy = random.randint(-self.shake_strength, self.shake_strength)

        # drag shadow
        if self.mode == "drag" and pix and not pix.isNull():
            painter.save()
            painter.setOpacity(0.22)
            sw = int(pix.width() * 0.55)
            sh = max(6, int(pix.height() * 0.12))
            sx = (self.width() // 2) - (sw // 2) + dx
            sy = self.char_y + pix.height() - (sh // 2) + dy
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.black)
            painter.drawEllipse(sx, sy, sw, sh)
            painter.restore()

        if pix and not pix.isNull():
            painter.drawPixmap(dx, dy + self.char_y, pix)

        if self.say_text and time.time() > self.say_until:
            self.say_text = ""

        if self.say_text:
            painter.setFont(QFont("Segoe UI", 10))

            bubble_w = self.bubble.width() if self.bubble else int(180 * HOUSE_SCALE_CHAR)
            bubble_h = self.bubble.height() if self.bubble else int(50 * HOUSE_SCALE_CHAR)

            head_x = self.width() // 2
            head_y = self.char_y + int(pix.height() * 0.4)
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

        self.setWindowTitle("집")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        if app_icon:
            self.setWindowIcon(app_icon)

        self.setFixedSize(HOUSE_WIN_W, HOUSE_WIN_H)

        self.default_bg = QPixmap(str(BG_DEFAULT_PATH)) if BG_DEFAULT_PATH.exists() else QPixmap()
        if not self.default_bg.isNull():
            self.default_bg = self.default_bg.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        self.bg_pix: Dict[str, Dict[str, QPixmap]] = {cat: {} for cat in BG_CATEGORIES}
        self.reload_bg_pixmaps()

        # ✅ init order (AttributeError 방지)
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
        self.placement_btn = QPushButton("배치", self)
        self.placement_btn.setCursor(Qt.PointingHandCursor)
        self.placement_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,178); border: 1px solid rgba(0,0,0,60);
                border-radius: 10px; padding: 6px 12px;
                font-weight: 900; min-height: 30px;
            }
            QPushButton:hover { background: rgba(255,255,255,210); }
        """)
        self.placement_btn.adjustSize()
        self.placement_btn.clicked.connect(self.open_placement_panel)

        self.furn_shop_btn = QPushButton("가구상점", self)
        self.furn_shop_btn.setCursor(Qt.PointingHandCursor)
        self.furn_shop_btn.setStyleSheet(self.placement_btn.styleSheet())
        self.furn_shop_btn.adjustSize()
        self.furn_shop_btn.clicked.connect(self.open_furniture_shop)

        self._reposition_overlay_ui()

        # pet
        self.house_pet = HousePetWidget(self.state, parent=self)
        self.house_pet.raise_()

        # ✅ deco overlay (펫보다 위)
        self.deco_overlay = DecoOverlay(self, self._overlay_pixmaps)
        self.deco_overlay.raise_()

        self._raise_overlay_ui()

    # ----------------
    # overlay ui
    # ----------------
    def _overlay_pixmaps(self) -> Dict[str, Optional[QPixmap]]:
        # deco는 펫 위에 올릴 거라 오버레이가 담당
        deco_id = self.state.selected_bg.get("deco")
        pm = None
        if deco_id and deco_id in self.bg_pix.get("deco", {}):
            pm = self.bg_pix["deco"][deco_id]
        return {"deco": pm}

    def _raise_overlay_ui(self):
        self.placement_btn.raise_()
        self.furn_shop_btn.raise_()
        if getattr(self, "house_pet", None):
            self.house_pet.raise_()
        if getattr(self, "deco_overlay", None):
            self.deco_overlay.raise_()
        pp = getattr(self, "placement_panel", None)
        if pp:
            pp.raise_()
        fs = getattr(self, "furniture_shop", None)
        if fs:
            fs.raise_()

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
        if getattr(self, "deco_overlay", None):
            self.deco_overlay.show()
            self.deco_overlay.raise_()

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

        if getattr(self, "deco_overlay", None):
            self.deco_overlay.resize(self.size())

        self.update()

    # ----------------
    # open panels (동시 오픈 금지)
    # ----------------
    def _close_panels_for_exclusive_open(self, who: str):
        """
        who == "placement" 이면 shop 닫고, who == "shop" 이면 placement 닫기
        깜빡임 방지.
        """
        if who == "placement":
            if self.furniture_shop and self.furniture_shop.isVisible():
                self.furniture_shop.close()
        elif who == "shop":
            if self.placement_panel and self.placement_panel.isVisible():
                self.placement_panel.close()

    def open_furniture_shop(self):
        self._close_panels_for_exclusive_open("shop")

        if self.furniture_shop and self.furniture_shop.isVisible():
            self.furniture_shop.raise_()
            self.furniture_shop.activateWindow()
            return

        self.furniture_shop = FurnitureShopWindow(
            self.state, app_icon=self.app_icon, on_purchased=self._on_layer_changed
        )
        self.furniture_shop.show()
        self.furniture_shop.raise_()
        self.furniture_shop.activateWindow()
        self._raise_overlay_ui()

    def open_placement_panel(self):
        self._close_panels_for_exclusive_open("placement")

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
        if getattr(self, "deco_overlay", None):
            self.deco_overlay.update()

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
        owned = getattr(self.state, "owned_bg", {}).get("wheel", set())
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

    def maybe_snap_to_wheel(self, pet_top_left: QPoint, pet_size: QSize, is_sleeping: bool) -> Optional[QPoint]:
        if is_sleeping:
            return None
        if not self._has_owned_selected_wheel():
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

    def handle_pet_dropped(self, pet_widget: HousePetWidget, is_sleeping: bool):
        if is_sleeping:
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
            snapped = self.maybe_snap_to_wheel(pet_widget.pos(), pet_widget.size(), is_sleeping=False)
            if snapped is not None:
                pet_widget.move(snapped)
            self.start_wheel_spin(pet_widget)

    # ----------------
    # pet auto ride
    # ----------------
    def try_auto_wheel_ride(self, pet_widget: HousePetWidget) -> bool:
        """
        펫이 가끔 스스로 쳇바퀴를 돌리는 행동.
        조건:
        - wheel 소지 + 배치
        - 수면/드래그 아님
        - 이미 회전 중 아님
        """
        if self.wheel_spinning:
            return False
        if pet_widget.sleeping or pet_widget.dragging:
            return False
        if not self._has_owned_selected_wheel():
            return False

        # 확률 (원하면 조절)
        if random.random() > 0.12:
            return False

        snapped = self.maybe_snap_to_wheel(pet_widget.pos(), pet_widget.size(), is_sleeping=False)
        if snapped is None:
            # 스냅 판정이 안 나면 그냥 강제로 스냅 위치로 이동
            zone = self._wheel_zone_rect()
            tx = zone.center().x()
            ty = zone.bottom()
            snapped = QPoint(tx - (pet_widget.width() // 2), (ty - pet_widget.height()) + WHEEL_SNAP_Y_OFFSET)

        pet_widget.move(snapped)
        pet_widget.on_wheel = True
        self.start_wheel_spin(pet_widget)
        return True

    # ----------------
    # wheel spin control
    # ----------------
    def start_wheel_spin(self, pet_widget: HousePetWidget):
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
        pet_widget.say("찍! 쳇바퀴다!", 1.6)

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

        # ✅ 1) 배경
        wp_id = self.state.selected_bg.get("wallpaper")
        if wp_id and wp_id in self.bg_pix.get("wallpaper", {}):
            painter.drawPixmap(0, 0, self.bg_pix["wallpaper"][wp_id])
        else:
            if not self.default_bg.isNull():
                painter.drawPixmap(0, 0, self.default_bg)
            else:
                painter.fillRect(self.rect(), Qt.white)

        # ✅ 2) 집/가구 (house, flower)
        for cat in ["house", "flower"]:
            sel = self.state.selected_bg.get(cat)
            if sel and sel in self.bg_pix.get(cat, {}):
                painter.drawPixmap(0, 0, self.bg_pix[cat][sel])

        # ✅ 3) 쳇바퀴 (wheel)
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

        # ✅ 4) deco는 오버레이 위젯이 그린다(펫 위로)
        self._raise_overlay_ui()