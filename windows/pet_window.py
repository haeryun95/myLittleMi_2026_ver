"""
windows/pet_window.py - 데스크탑 위에 떠다니는 펫 창
- 드래그 시 asset/animation/draging 프레임 애니메이션
- ControlPanel 채팅 연동: send_chat_from_panel 구현(로그에 답변 + 말풍선)

✅ Climb 요구사항 반영(고요 버전)
1) 유저가 드래그로 펫을 화면 끝(위, 오른쪽, 왼쪽) 에 놔두면 climb 시작
2) 혹은 무작위로도 시작. 가장 가까운 곳(왼/오/천장) 선택
   - 동점이면 천장보다 왼/오 우선
2-1) 방향별 이미지 처리
   - 오른쪽 벽: 원본
   - 왼쪽 벽: 좌우반전
   - 천장: 시계방향 90도 회전
   - 천장에서 "왼쪽 이동"일 때: (시계방향 90도 회전) + (좌우반전 추가)
3) climb 동안 hold(>=2초 랜덤) ↔ move(랜덤) 반복
   - move 동안에만 프레임 순환 + 이동 발생
   - 프레임 1회 진행마다 20px 이동(벽: 위/아래, 천장: 좌/우)
4) climb 종료 시 화면 아래쪽 중앙 부근에 뛰어내림
"""
import random
import time
import json
from typing import List, Optional
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QRect, QTimer
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QWidget

from config import (
    ANIM_DIR, ANIM_SPEED_MS, BUBBLE_PADDING, BUBBLE_PATH,
    EAT_SHAKE_DURATION, EAT_SHAKE_STRENGTH, FACE_HOLD_SEC,
    NORMAL_RANDOM_INTERVAL, SCALE_BUBBLE, SCALE_CHAR,
    SLEEP_DURATION_SEC, SLEEP_RECOVER_ENERGY, WANDER_INTERVAL_MS_RANGE,
)
from state import PetState, clamp
from utils.image_loader import load_folder_pixmaps_as_map, load_folder_pixmaps_as_list, make_flipped_frames
from body import apply_ai_result

try:
    from groq_api import call_groq_chat
except Exception:
    call_groq_chat = None


def _transform_pixmap_centered(pix: QPixmap, rotate_deg: float = 0.0, flip_x: bool = False) -> QPixmap:
    """pix를 중심 기준으로 회전/반전한 새 QPixmap 반환."""
    if pix is None or pix.isNull():
        return pix

    w, h = pix.width(), pix.height()
    t = QTransform()
    t.translate(w / 2, h / 2)

    if rotate_deg:
        t.rotate(rotate_deg)

    if flip_x:
        t.scale(-1, 1)

    t.translate(-w / 2, -h / 2)
    return pix.transformed(t, Qt.SmoothTransformation)


class PetWindow(QWidget):
    def __init__(self, state: PetState, app_icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state

        self.press_pos: Optional[QPoint] = None
        self.was_dragged = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if app_icon:
            self.setWindowIcon(app_icon)

        self.current_action_pixmap = None
        self.idle_until = 0.0

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

        # 신규 모션
        self.dance_frames = load_folder_pixmaps_as_list(ANIM_DIR / "dance", SCALE_CHAR)
        self.snooze_frames = load_folder_pixmaps_as_list(ANIM_DIR / "snooze", SCALE_CHAR)
        self.climb_frames = load_folder_pixmaps_as_list(ANIM_DIR / "climb", SCALE_CHAR)  # 고요: 2장

        self.walk_frames_flipped = make_flipped_frames(self.walk_frames) if self.walk_frames else []
        self.sit_frames_flipped = make_flipped_frames(self.sit_frames) if self.sit_frames else []
        self.drag_frames_flipped = make_flipped_frames(self.drag_frames) if self.drag_frames else []

        # ✅ climb 프레임 변형을 "미리" 만들어 둠 (paintEvent에서 즉석 변형 금지)
        # - right 벽: 원본
        # - left 벽: 좌우 반전
        # - top: 시계방향 90도(= Qt -90)
        # - top + left move: 회전(-90) + 좌우반전
        self.climb_frames_right = self.climb_frames[:] if self.climb_frames else []
        self.climb_frames_left = make_flipped_frames(self.climb_frames) if self.climb_frames else []
        self.climb_frames_top = [_transform_pixmap_centered(p, rotate_deg=-90, flip_x=False) for p in self.climb_frames] if self.climb_frames else []
        self.climb_frames_top_leftmove = [_transform_pixmap_centered(p, rotate_deg=-90, flip_x=True) for p in self.climb_frames] if self.climb_frames else []

        # ✅ Climb 상태머신 변수
        self.is_climbing = False
        self.climb_surface = ""  # 'left', 'right', 'top'
        self.climb_dir = 1       # left/right: +1=down -1=up, top: +1=right -1=left

        self.climb_phase = "hold"        # 'hold' or 'move'
        self.climb_phase_until = 0.0
        self.climb_total_end_at = 0.0

        self.climb_hold_min = 2.0
        self.climb_hold_max = 4.0
        self.climb_move_min = 0.8
        self.climb_move_max = 2.2

        self.climb_anim_ms = 120
        self.climb_step_px = 20

        # ✅ drop(아래 중앙으로 뛰어내리기)
        self.is_dropping = False
        self.drop_target_x = 0

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
        self.char_y = self.bubble_h  # 스프라이트가 그려지는 y 오프셋(말풍선 공간)

        self.screen_rect = QApplication.primaryScreen().availableGeometry()
        self.move(
            random.randint(self.screen_rect.left(), max(self.screen_rect.left(), self.screen_rect.right() - self.width())),
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
        self.current_face = self.state.last_face if self.state.last_face in self.emotion_map else random.choice(self.normal_faces or keys)
        self.next_normal_change = time.time() + NORMAL_RANDOM_INTERVAL
        self.face_until = 0.0

        self.shake_until = 0.0
        self.shake_strength = 0

        self.vx = random.choice([-2, -1, 1, 2])
        self.facing_left = False
        self.vy = 0
        self.gravity = 1
        self.ground_y = self.y()

        self.sleeping = False
        self.sleep_end_at = 0.0

        self.random_dialogues = []
        self._load_dialogues()

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
    # 스프라이트 기준 좌표(벽/천장 딱 붙기)
    # -----------------------------
    def _sprite_left(self) -> int:
        return self.x()

    def _sprite_right(self) -> int:
        return self.x() + self.char_w

    def _sprite_top(self) -> int:
        return self.y() + self.char_y

    def _sprite_bottom(self) -> int:
        return self.y() + self.char_y + self.char_h

    def _snap_to_surface(self, surface: str):
        """스프라이트가 벽/천장에 '딱 붙게' 윈도우 좌표를 스냅."""
        s = self.screen_rect
        x, y = self.x(), self.y()

        if surface == "left":
            x = s.left()
        elif surface == "right":
            x = s.right() - self.char_w
        elif surface == "top":
            y = s.top() - self.char_y

        self.move(int(x), int(y))

    def _pick_nearest_climb_surface(self) -> str:
        """가장 가까운 면 선택. 동점이면 천장보다 좌/우 우선."""
        s = self.screen_rect
        dist_left = abs(self._sprite_left() - s.left())
        dist_right = abs(s.right() - self._sprite_right())
        dist_top = abs(self._sprite_top() - s.top())

        m = min(dist_left, dist_right, dist_top)
        candidates = []
        if dist_left == m:
            candidates.append("left")
        if dist_right == m:
            candidates.append("right")
        if dist_top == m:
            candidates.append("top")

        if "top" in candidates and ("left" in candidates or "right" in candidates):
            candidates = [c for c in candidates if c != "top"]

        return random.choice(candidates) if candidates else "right"

    # -----------------------------
    # climb state machine
    # -----------------------------
    def _schedule_next_climb_phase(self, now: float):
        """hold/move 전환 스케줄 + move일 때만 anim_timer를 빠르게 돌림."""
        if self.climb_phase == "hold":
            self.climb_phase_until = now + random.uniform(self.climb_hold_min, self.climb_hold_max)
            # hold 동안은 모션(프레임) 멈춤
            self.anim_timer.stop()
        else:
            self.climb_phase_until = now + random.uniform(self.climb_move_min, self.climb_move_max)
            self.climb_anim_ms = random.randint(90, 170)
            self.anim_timer.start(self.climb_anim_ms)

    def _start_climb(self, surface: Optional[str] = None):
        if self.dragging or self.sleeping or self.is_climbing or self.is_dropping:
            return
        if not self.climb_frames:
            return

        now = time.time()
        self.is_climbing = True
        self.climb_surface = surface or self._pick_nearest_climb_surface()

        # 총 지속 시간 (원하면 30초 고정 가능)
        self.climb_total_end_at = now + random.uniform(8.0, 18.0)

        # 표면에 딱 붙게 스냅
        self._snap_to_surface(self.climb_surface)

        # 방향 초기화
        self.climb_dir = random.choice([-1, 1])
        self.vx = 0
        self.vy = 0

        # hold부터 시작
        self.climb_phase = "hold"
        self._schedule_next_climb_phase(now)

        self.set_mode("climb", sec=99999)

    def _climb_step(self):
        """move 단계에서만: 프레임 1회 진행마다 20px 이동."""
        if not self.is_climbing or self.climb_phase != "move":
            return

        s = self.screen_rect
        x, y = self.x(), self.y()
        step = self.climb_dir * self.climb_step_px

        if self.climb_surface in ("left", "right"):
            y += step
            # 스프라이트 top이 천장 넘지 않게
            min_y = s.top() - self.char_y
            # 스프라이트 bottom이 바닥 넘지 않게
            max_y = s.bottom() - (self.char_y + self.char_h)

            if y <= min_y:
                y = min_y
                self.climb_dir *= -1
            elif y >= max_y:
                y = max_y
                self.climb_dir *= -1

        elif self.climb_surface == "top":
            x += step
            min_x = s.left()
            max_x = s.right() - self.char_w

            if x <= min_x:
                x = min_x
                self.climb_dir *= -1
            elif x >= max_x:
                x = max_x
                self.climb_dir *= -1

            # 천장은 계속 붙어있어야 함
            y = s.top() - self.char_y

        # 표면에 딱 붙게 축 보정
        if self.climb_surface == "left":
            x = s.left()
        elif self.climb_surface == "right":
            x = s.right() - self.char_w
        elif self.climb_surface == "top":
            y = s.top() - self.char_y

        self.move(int(x), int(y))

    def _start_drop_to_bottom_center(self):
        s = self.screen_rect
        self.is_dropping = True

        center_x = (s.left() + s.right() - self.char_w) // 2
        self.drop_target_x = int(center_x + random.randint(-60, 60))

        # 살짝 튀고 낙하
        self.vy = -8
        self.set_mode("normal", sec=99999)

    # -----------------------------
    # existing
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

    def start_shake(self, sec: float = 0.6, strength: int = 4):
        self.shake_until = time.time() + sec
        self.shake_strength = max(1, int(strength))
        self.update()

    def do_jump(self, strength: int = 12):
        floor_y = min(self.ground_y, self.screen_rect.bottom() - self.height())
        if abs(self.y() - floor_y) <= 2:
            self.vy = -abs(int(strength))

    def set_mode(self, mode: str, sec: float = 1.5):
        if mode not in ("normal", "walk", "sleep", "speak", "eat", "drag", "sit", "dance", "snooze", "climb"):
            mode = "normal"

        self.mode = mode
        self.frame_i = 0
        self.mode_until = time.time() + float(sec)

        if mode == "eat" and self.eat_frames:
            self.current_action_pixmap = random.choice(self.eat_frames)
        else:
            self.current_action_pixmap = None

        if mode in ANIM_SPEED_MS:
            self.anim_timer.start(ANIM_SPEED_MS[mode])
        elif mode == "climb":
            # ✅ climb은 phase가 anim_timer를 제어함
            # (여기서 start/stop 하지 않음)
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

    def trigger_eat_visual(self):
        self.set_mode("eat", sec=1.5)
        self.start_shake(sec=EAT_SHAKE_DURATION, strength=EAT_SHAKE_STRENGTH)

    def start_sleep_for_60s(self):
        if self.sleeping:
            return
        self.sleeping = True
        self.sleep_end_at = time.time() + SLEEP_DURATION_SEC
        self.set_mode("sleep", sec=SLEEP_DURATION_SEC + 0.2)
        self.say("찍… 졸려… 잠깐 잘게…", duration=2.4)

    def show_bubble(self, text: str, bubble_sec: float = 2.2):
        self.say(text, duration=bubble_sec)

    def auto_wander(self):
        self.wander_timer.start(random.randint(*WANDER_INTERVAL_MS_RANGE))
        if self.dragging or self.sleeping or self.is_climbing or self.is_dropping:
            return
        if self.mode in ("eat", "speak", "sleep", "drag", "climb"):
            return

        # ✅ 무작위 climb 시작
        if random.random() < 0.04:
            self._start_climb(None)
            return

        rand = random.random()
        if rand < 0.10:
            self.set_mode("dance", sec=random.uniform(2.0, 5.0))
        elif rand < 0.20:
            self.set_mode("snooze", sec=random.uniform(2.0, 5.0))
        elif rand < 0.35:
            self.facing_left = random.choice([True, False])
            self.set_mode("sit", sec=random.uniform(2.0, 4.0))
        elif rand < 0.75:
            self.vx = random.choice([-3, -2, -1, 1, 2, 3])
            self.set_mode("walk", sec=random.uniform(1.5, 3.5))
        else:
            self.set_mode("normal", sec=random.uniform(1.0, 2.0))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = True
            self.was_dragged = False
            self.press_pos = e.globalPosition().toPoint()
            self.drag_offset = self.press_pos - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)

            if not self.sleeping and self.drag_frames:
                self.set_mode("drag", sec=99999)
            e.accept()

    def mouseMoveEvent(self, e):
        if self.dragging:
            current_pos = e.globalPosition().toPoint()
            diff_x = (current_pos - self.press_pos).x()
            if diff_x < 0:
                self.facing_left = True
            elif diff_x > 0:
                self.facing_left = False
            if self.press_pos and (current_pos - self.press_pos).manhattanLength() > 4:
                self.was_dragged = True
            self.move(current_pos - self.drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.OpenHandCursor)
            self.ground_y = min(self.y(), self.screen_rect.bottom() - self.height())

            if self.sleeping:
                remain = max(0.1, self.sleep_end_at - time.time())
                self.set_mode("sleep", sec=remain)
            else:
                if self.mode == "drag":
                    self.set_mode("normal", sec=99999)

            # ✅ 드래그로 화면 끝(좌/우/천장)에 "스프라이트"가 닿아있으면 climb 시작
            if self.was_dragged and (not self.sleeping) and (not self.is_climbing) and (not self.is_dropping):
                s = self.screen_rect
                pad = 1
                at_left = self._sprite_left() <= s.left() + pad
                at_right = self._sprite_right() >= s.right() - pad
                at_top = self._sprite_top() <= s.top() + pad

                if at_left or at_right or at_top:
                    surface = self._pick_nearest_climb_surface()
                    self._start_climb(surface)

            if not self.was_dragged:
                self.on_pet_clicked()
            e.accept()

    def on_pet_clicked(self):
        # ✅ 클릭 시 climb 해제
        if self.is_climbing:
            self.is_climbing = False
            self.climb_phase = "hold"
            self.anim_timer.start(200)
            self.set_mode("normal", sec=99999)

        if self.sleeping:
            self.start_shake(sec=0.3, strength=3)
            self.say("음냐... 졸려... 더 잘래 찍...", 1.8)
            remaining_sleep = max(0.1, self.sleep_end_at - time.time())
            self.set_mode("sleep", sec=remaining_sleep)
            return

        self.start_shake(sec=0.4, strength=3)
        msg = random.choice(["헤헤…", "찍찍… 좋아!", "쓰담쓰담…", "기분 좋아…"])
        self.say(msg, 2.0)
        self.state.apply_delta({"fun": +3, "mood": +6, "energy": 0, "hunger": -0.5})

    def advance_frame(self):
        # ✅ climb은 move 단계에서만 프레임이 진행 + 이동도 같이 발생
        if self.mode == "climb" and self.is_climbing:
            if self.climb_phase != "move":
                return
            self._climb_step()

        mode_map = {
            "walk": self.walk_frames,
            "sleep": self.sleep_frames,
            "speak": self.speak_frames,
            "drag": self.drag_frames,
            "sit": self.sit_frames,
            "dance": self.dance_frames,
            "snooze": self.snooze_frames,
            "climb": self.climb_frames,
        }
        frames = mode_map.get(self.mode)
        if frames:
            self.frame_i = (self.frame_i + 1) % len(frames)
        elif self.mode == "eat":
            self.frame_i += 1
        self.update()

    def tick_logic(self):
        now = time.time()

        if int(now * 10) % 20 == 0:
            self.raise_()

        if now < self.shake_until:
            self.update()

        if self.sleeping:
            if now >= self.sleep_end_at or self.state.energy >= 99.9:
                self.sleeping = False
                self.state.energy = clamp(self.state.energy, 0, 100)
                self.state.mood = clamp(self.state.mood + 5)
                self.say("찍! 좀 나아졌어…", 2.2)
                self.set_mode("normal", 99999)
            else:
                if self.mode != "sleep" and now > self.say_until:
                    self.set_mode("sleep", sec=max(0.1, self.sleep_end_at - now))
                self.state.energy = clamp(self.state.energy + 0.05, 0, 100)
            return

        if self.mode == "normal" and now > self.face_until and now >= self.next_normal_change:
            mood = self.state.mood
            if mood < 30:
                pool = self.sad_faces or self.normal_faces
            elif mood > 70:
                pool = [k for k in self.emotion_map if "happy" in k.lower()] + self.normal_faces
            else:
                pool = self.normal_faces
            if pool:
                self.current_face = random.choice(pool)
            self.next_normal_change = now + NORMAL_RANDOM_INTERVAL

        if self.mode == "normal" and not self.dragging and now > self.say_until:
            if random.random() < 0.0005:
                if self.random_dialogues:
                    self.say(random.choice(self.random_dialogues), 3.0)
                    self.set_mode("speak", sec=3.0)

        if not self.dragging:
            x, y = self.x(), self.y()
            s = self.screen_rect

            # ✅ drop 처리
            if self.is_dropping:
                dx = self.drop_target_x - x
                if abs(dx) > 2:
                    x += int(dx * 0.15)
                else:
                    x = self.drop_target_x

                self.vy += self.gravity
                y += self.vy

                floor_y = s.bottom() - (self.char_y + self.char_h)
                if y >= floor_y:
                    y = floor_y
                    self.vy = 0
                    self.is_dropping = False
                    self.set_mode("normal", sec=99999)

                self.move(int(x), int(y))
                self.update()
                return

            # ✅ climb 상태 처리
            if self.is_climbing:
                # 항상 표면에 딱 붙기
                self._snap_to_surface(self.climb_surface)

                # 종료 -> drop
                if now >= self.climb_total_end_at:
                    self.is_climbing = False
                    self.anim_timer.start(200)
                    self._start_drop_to_bottom_center()
                    self.update()
                    return

                # hold/move 전환
                if now >= self.climb_phase_until:
                    self.climb_phase = "move" if self.climb_phase == "hold" else "hold"
                    self._schedule_next_climb_phase(now)

                # climb 중 기본 중력/걷기 스킵 (이동은 advance_frame에서만)
                self.update()
                return

            # 모드 자동 종료 (climb 제외)
            if now > self.mode_until and self.mode in ("walk", "sleep", "speak", "eat", "sit", "dance", "snooze"):
                self.set_mode("normal", 99999)

            # 바닥(스프라이트 기준)
            floor_y = s.bottom() - (self.char_y + self.char_h)

            # 걷기
            if self.mode == "walk":
                x += self.vx
                if x <= s.left() or x + self.char_w >= s.right():
                    self.vx *= -1

            # 중력
            self.vy += self.gravity
            y += self.vy

            if y >= floor_y:
                y, self.vy = floor_y, 0

            self.move(int(x), int(y))

        self.update()

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
                # ✅ 고요 요구사항: 2장 프레임
                idx = self.frame_i % len(self.climb_frames)

                if self.climb_surface == "right":
                    pix = self.climb_frames_right[idx]
                elif self.climb_surface == "left":
                    # 1) 왼쪽 벽: 좌우반전 ONLY
                    pix = self.climb_frames_left[idx]
                elif self.climb_surface == "top":
                    # 2) 천장: 시계방향 90도
                    # 2-1) 천장에서 왼쪽 이동(climb_dir=-1)이면 회전+좌우반전 추가
                    if self.climb_dir == -1:
                        pix = self.climb_frames_top_leftmove[idx]
                    else:
                        pix = self.climb_frames_top[idx]
                else:
                    pix = self.climb_frames_right[idx]

            elif self.mode == "dance" and self.dance_frames:
                pix = self.dance_frames[self.frame_i % len(self.dance_frames)]
            elif self.mode == "snooze" and self.snooze_frames:
                pix = self.snooze_frames[self.frame_i % len(self.snooze_frames)]
            elif self.mode == "eat" and self.current_action_pixmap:
                pix = self.current_action_pixmap
            elif self.mode == "speak" and self.speak_frames:
                pix = self.speak_frames[self.frame_i % len(self.speak_frames)]
            elif self.mode == "sit" and self.sit_frames:
                frames = self.sit_frames_flipped if self.facing_left else self.sit_frames
                pix = frames[self.frame_i % len(frames)]
            elif self.mode == "walk" and self.walk_frames:
                frames = self.walk_frames_flipped if self.vx < 0 else self.walk_frames
                pix = frames[self.frame_i % len(frames)]
            elif self.mode == "sleep" and self.sleep_frames:
                pix = self.sleep_frames[self.frame_i % len(self.sleep_frames)]
            else:
                mood = self.state.mood
                target_key = "happy" if mood > 70 else "sad" if mood < 30 else "normal"
                matches = [k for k in self.emotion_map.keys() if target_key in k.lower()]
                face_key = matches[0] if matches else self.current_face
                pix = self.emotion_map.get(face_key) or next(iter(self.emotion_map.values()))

            dx = dy = 0
            if now < self.shake_until and self.shake_strength > 0:
                dx = random.randint(-self.shake_strength, self.shake_strength)
                dy = random.randint(-self.shake_strength, self.shake_strength)

            if pix:
                painter.drawPixmap(dx, dy + self.char_y, pix)

                if self.say_text and now < self.say_until:
                    font = QFont("Galmuri11", 10)
                    font.setBold(True)
                    painter.setFont(font)

                    bw = self.bubble.width() if self.bubble else 120
                    bh = self.bubble.height() if self.bubble else 45
                    bx = (self.width() - bw) // 2
                    by = max(0, self.char_y - bh + 25) + dy

                    bubble_rect = QRect(bx + dx, by, bw, bh)

                    if self.bubble:
                        painter.drawPixmap(bx + dx, by, self.bubble)
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

    def send_chat_from_panel(self, user_text: str):
        """컨트롤패널에서 온 텍스트를 AI에 보내고, 결과를 말풍선/상태에 반영."""
        if not call_groq_chat:
            self.say("찍... 연결이 안 됐어.", 2.0)
            return

        self.set_mode("speak", sec=5.0)
        self.say("음... 잠깐만 찍!", 2.0)

        try:
            # 응답 생성
            ai_text = call_groq_chat(user_text)

            # AI 결과를 상태에 반영(프로젝트 로직)
            try:
                apply_ai_result(self.state, ai_text)
            except Exception:
                pass

            # 말하기
            if ai_text:
                self.say(str(ai_text), 3.0)
                self.set_mode("speak", sec=3.0)
            else:
                self.say("찍... 대답이 비었어.", 2.0)

        except Exception:
            self.say("찍... 오류가 났어.", 2.0)
        finally:
            # 말 끝나면 normal로 복귀
            self.set_mode("normal", sec=99999)