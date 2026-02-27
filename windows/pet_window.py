"""
windows/pet_window.py - 데스크탑 위에 떠다니는 펫 창
- 드래그 시 asset/animation/draging 프레임 애니메이션
- ControlPanel 채팅 연동: send_chat_from_panel 구현(로그에 답변 + 말풍선)
"""
import random
import time
from typing import List, Optional

from PySide6.QtCore import Qt, QPoint, QRect, QTimer
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
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

        # ✅ drag animation frames
        self.drag_frames = load_folder_pixmaps_as_list(ANIM_DIR / "draging", SCALE_CHAR)
        self.drag_frames_flipped = make_flipped_frames(self.drag_frames) if self.drag_frames else []

        self.walk_frames_flipped = make_flipped_frames(self.walk_frames) if self.walk_frames else []

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
        self.bubble_h = self.bubble.height() if self.bubble else int(60 * SCALE_CHAR)

        self.resize(self.char_w, self.char_h + self.bubble_h)
        self.char_y = self.bubble_h

        # start position
        self.screen_rect = QApplication.primaryScreen().availableGeometry()
        self.move(
            random.randint(self.screen_rect.left(), max(self.screen_rect.left(), self.screen_rect.right() - self.width())),
            self.screen_rect.bottom() - self.height(),
        )

        # drag
        self.dragging = False
        self.drag_offset = QPoint(0, 0)
        self.setCursor(Qt.OpenHandCursor)

        # speech
        self.say_text = ""
        self.say_until = 0.0

        # mode
        self.mode = "normal"
        self.frame_i = 0
        self.mode_until = time.time() + 99999

        self.current_face = self.state.last_face if self.state.last_face in self.emotion_map else random.choice(self.normal_faces or keys)
        self.next_normal_change = time.time() + NORMAL_RANDOM_INTERVAL
        self.face_until = 0.0

        self.shake_until = 0.0
        self.shake_strength = 0

        # movement
        self.vx = random.choice([-2, -1, 1, 2])
        self.vy = 0
        self.gravity = 1
        self.ground_y = self.y()

        # sleep
        self.sleeping = False
        self.sleep_end_at = 0.0

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

    # -------------------------
    # public api
    # -------------------------
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
        if mode not in ("normal", "walk", "sleep", "speak", "eat", "drag"):
            mode = "normal"
        self.mode = mode
        self.frame_i = 0
        if mode in ANIM_SPEED_MS:
            self.anim_timer.start(ANIM_SPEED_MS[mode])
        else:
            self.anim_timer.start(90 if mode == "drag" else 999999)
        self.mode_until = time.time() + float(sec)
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
        self.say("찍… 졸려… 잠깐 잘게…", duration=2.4)

    # -------------------------
    # movement/interaction
    # -------------------------
    def auto_wander(self):
        self.wander_timer.start(random.randint(*WANDER_INTERVAL_MS_RANGE))
        if self.dragging or self.sleeping:
            return
        if self.mode in ("walk", "sleep", "eat", "speak", "drag"):
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

            # ✅ drag mode
            if self.drag_frames:
                self.set_mode("drag", sec=99999)
            e.accept()

    def mouseMoveEvent(self, e):
        if self.dragging:
            current_pos = e.globalPosition().toPoint()
            if self.press_pos and (current_pos - self.press_pos).manhattanLength() > 4:
                self.was_dragged = True
            self.move(current_pos - self.drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.OpenHandCursor)
            self.ground_y = min(self.y(), self.screen_rect.bottom() - self.height())

            # drag mode end
            if self.mode == "drag":
                self.set_mode("normal", sec=99999)

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
        elif self.mode == "drag" and self.drag_frames:
            self.frame_i = (self.frame_i + 1) % len(self.drag_frames)
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
            low = (
                (self.state.mood <= 35) or (self.state.fun <= 20)
                or (self.state.energy <= 20) or (self.state.hunger <= 18)
            )
            pool = self.sad_faces if (low and self.sad_faces) else (self.normal_faces or list(self.emotion_map.keys()))
            self.current_face = random.choice(pool)
            self.state.last_face = self.current_face
            self.next_normal_change = now + NORMAL_RANDOM_INTERVAL

        if (not self.sleeping) and (not self.dragging) and now > self.mode_until and self.mode in ("walk", "sleep", "speak", "eat"):
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

        # choose sprite
        if self.mode == "drag" and self.drag_frames:
            pix = (
                self.drag_frames_flipped[self.frame_i]
                if (self.vx < 0 and self.drag_frames_flipped)
                else self.drag_frames[self.frame_i]
            )
        elif self.mode == "walk" and self.walk_frames:
            pix = (
                self.walk_frames_flipped[self.frame_i]
                if (self.vx < 0 and self.walk_frames_flipped)
                else self.walk_frames[self.frame_i]
            )
        elif self.mode == "sleep" and self.sleep_frames:
            pix = self.sleep_frames[self.frame_i]
        elif self.mode == "speak" and self.speak_frames:
            pix = self.speak_frames[self.frame_i]
        elif self.mode == "eat" and self.eat_frames:
            pix = self.eat_frames[self.frame_i % len(self.eat_frames)]
        else:
            pix = self.emotion_map.get(self.current_face) or next(iter(self.emotion_map.values()))

        # shake
        dx = dy = 0
        if time.time() < self.shake_until and self.shake_strength > 0:
            dx = random.randint(-self.shake_strength, self.shake_strength)
            dy = random.randint(-self.shake_strength, self.shake_strength)

        painter.drawPixmap(dx, dy + self.char_y, pix)

        # bubble
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

    # -------------------------
    # ✅ ControlPanel 연동 핵심
    # -------------------------
    def send_chat_from_panel(self, msg: str, chat_log):
        """
        ControlPanel에서 채팅 전송 시 호출
        - AI 결과를 말풍선/표정/상태에 적용
        - chat_log에 '찍찍이: ...' 형식으로 출력
        """
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
                # fallback
                result = {
                    "reply": "찍… (AI 연결이 없어서 그냥 대답중!)",
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
            try:
                chat_log.append(f"[오류] AI 처리 실패: {ex}")
            except Exception:
                pass