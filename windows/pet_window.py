"""
windows/pet_window.py - 데스크탑 위에 떠다니는 펫 창
- 드래그 시 asset/animation/draging 프레임 애니메이션
- ControlPanel 채팅 연동: send_chat_from_panel 구현(로그에 답변 + 말풍선)
"""
import random
import time
import json
from typing import List, Optional
from pathlib import Path

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

        # ✅ 최상단 고정 플래그 유지
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if app_icon:
            self.setWindowIcon(app_icon)
        
        self.current_action_pixmap = None  # 액션 시 고정할 이미지 저장용
        self.idle_until = 0.0              # 가만히 서 있는 시간 제어

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

        # ✅ drag animation frames
        self.drag_frames = load_folder_pixmaps_as_list(ANIM_DIR / "dragging", SCALE_CHAR)
        self.drag_frames_flipped = make_flipped_frames(self.drag_frames) if self.drag_frames else []

        self.walk_frames_flipped = make_flipped_frames(self.walk_frames) if self.walk_frames else []
        self.sit_frames_flipped = make_flipped_frames(self.sit_frames) if self.sit_frames else []

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
        self.facing_left = False
        self.vy = 0
        self.gravity = 1
        self.ground_y = self.y()

        # sleep
        self.sleeping = False
        self.sleep_end_at = 0.0

        # ✅ 랜덤 대화 데이터 로드
        self.random_dialogues = []
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

    def _load_dialogues(self):
        try:
            path = Path(__file__).resolve().parents[1] / "asset" / "data" / "dialogue.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.random_dialogues = data.get("random_talks", [])
        except Exception: pass

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
        if mode not in ("normal", "walk", "sleep", "speak", "eat", "drag", "sit"):
            mode = "normal"
        
        self.mode = mode
        self.frame_i = 0
        self.mode_until = time.time() + float(sec)

        # eat일 때 랜덤 1장 고정
        if mode == "eat" and self.eat_frames:
            self.current_action_pixmap = random.choice(self.eat_frames)
        else:
            self.current_action_pixmap = None

        # ✅ 애니메이션 속도 설정
        if mode in ANIM_SPEED_MS:
            self.anim_timer.start(ANIM_SPEED_MS[mode])
        elif mode == "sit":
            self.anim_timer.start(100) # 앉아 있을 때 프레임 전환 속도
        elif mode == "drag":
            self.anim_timer.start(90)
        else:
            self.anim_timer.start(999999) # normal 등은 정지
        
        self.update()

    def trigger_eat_visual(self):
        # ✅ set_mode 호출로 랜덤 이미지 고정 로직 실행
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
        if not hasattr(self, 'bubble_label'): return 
        self.bubble_label.setText(text)
        self.bubble_label.show()
        if hasattr(self, 'bubble_timer'): self.bubble_timer.stop()
        else:
            self.bubble_timer = QTimer(self)
            self.bubble_timer.setSingleShot(True)
            self.bubble_timer.timeout.connect(self.bubble_label.hide)
        self.bubble_timer.start(int(bubble_sec * 1000))

    # -------------------------
    # movement/interaction
    # -------------------------
    def auto_wander(self):
        self.wander_timer.start(random.randint(*WANDER_INTERVAL_MS_RANGE))
        if self.dragging or self.sleeping: return
        now = time.time()
        if self.mode in ("eat", "speak", "sleep", "drag"): return

        rand = random.random()
        if rand < 0.25: 
            self.facing_left = random.choice([True, False])
            self.set_mode("sit", sec=random.uniform(2.0, 4.0))
        elif rand < 0.70: 
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
            
            # ✅ 수정: 자는 중이 아닐 때만 drag 모드로 변경
            if not self.sleeping and self.drag_frames:
                self.set_mode("drag", sec=99999)
            e.accept()

    def mouseMoveEvent(self, e):
        if self.dragging:
            current_pos = e.globalPosition().toPoint()
            diff_x = (current_pos - self.press_pos).x()
            if diff_x < 0: self.facing_left = True
            elif diff_x > 0: self.facing_left = False
            if self.press_pos and (current_pos - self.press_pos).manhattanLength() > 4:
                self.was_dragged = True
            self.move(current_pos - self.drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.OpenHandCursor)
            self.ground_y = min(self.y(), self.screen_rect.bottom() - self.height())
            
            # ✅ 수정: 드래그 종료 후 상태 체크
            if self.sleeping:
                # 자는 중이면 다시 sleep 모드로 강제 복구
                remain = max(0.1, self.sleep_end_at - time.time())
                self.set_mode("sleep", sec=remain)
            else:
                # 안 자는 중이면 정상적으로 normal 복귀
                if self.mode == "drag":
                    self.set_mode("normal", sec=99999)
            
            if not self.was_dragged:
                self.on_pet_clicked()
            e.accept()

    def on_pet_clicked(self):
        if self.sleeping:
            self.start_shake(sec=0.3, strength=2)
            self.say("음냐... 졸려... 더 잘래 찍...", 1.8)
            # ✅ 말을 한 직후(혹은 동시에) 다시 sleep 모드로 고정
            # 모드 유지 시간을 수면 종료 시간까지 넉넉하게 잡음
            remaining_sleep = max(0.1, self.sleep_end_at - time.time())
            self.set_mode("sleep", sec=remaining_sleep)
            return
        self.start_shake(sec=0.35, strength=2)
        msg = random.choice(["헤헤…", "찍찍… 좋아!", "쓰담쓰담…", "기분 좋아…"])
        self.say(msg, 2.0)
        self.state.apply_delta({"fun": +3, "mood": +6, "energy": 0, "hunger": -0.5})

    def advance_frame(self):
        mode_map = {
            "walk": self.walk_frames, "sleep": self.sleep_frames,
            "speak": self.speak_frames, "drag": self.drag_frames, "sit": self.sit_frames
        }
        frames = mode_map.get(self.mode)
        if frames: self.frame_i = (self.frame_i + 1) % len(frames)
        elif self.mode == "eat": self.frame_i += 1
        self.update()

    def tick_logic(self):
        now = time.time()

        # ✅ 최상단 강제 유지
        if int(now * 10) % 20 == 0: self.raise_()

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
                self.state.energy = clamp(self.state.energy + 0.15, 0, 100)
            return

        # ✅ 표정 업데이트 (happy와 normal 믹싱)
        if self.mode == "normal" and now > self.face_until and now >= self.next_normal_change:
            mood = self.state.mood
            if mood < 30:
                pool = self.sad_faces or self.normal_faces
            elif mood > 70:
                happy_pool = [k for k in self.emotion_map.keys() if "happy" in k.lower()]
                pool = happy_pool + self.normal_faces # 섞어서 출력
            else:
                pool = self.normal_faces
            
            if pool:
                self.current_face = random.choice(pool)
                self.state.last_face = self.current_face
            self.next_normal_change = now + NORMAL_RANDOM_INTERVAL

        # ✅ 랜덤 말걸기 이벤트 (speak 프레임 적용)
        if self.mode == "normal" and not self.dragging and now > self.say_until:
            if random.random() < 0.0005: # 약 0.05% 확률
                if self.random_dialogues:
                    msg = random.choice(self.random_dialogues)
                    self.say(msg, 3.0)
                    # ✅ 말할 때 speak 모드를 활성화하여 애니메이션 출력
                    self.set_mode("speak", sec=3.0)

        if not self.dragging:
            if now > self.mode_until and self.mode in ("walk", "sleep", "speak", "eat", "sit"):
                self.set_mode("normal", 99999)
            
            x, y = self.x(), self.y()
            floor_y = min(self.ground_y, self.screen_rect.bottom() - self.height())
            if self.mode == "walk":
                x += self.vx
                if x <= self.screen_rect.left() or x + self.width() >= self.screen_rect.right(): self.vx *= -1
            self.vy += self.gravity
            y += self.vy
            if y >= floor_y: y, self.vy = floor_y, 0
            self.move(int(x), int(y))
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        try:
            now = time.time()
            pix = None

            # 1. 모드별 프레임 선택 (반전 로직 포함)
            if self.mode == "drag" and self.drag_frames:
                frames = self.drag_frames_flipped if self.facing_left else self.drag_frames
                pix = frames[self.frame_i % len(frames)]
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

            # 2. 흔들림 효과
            dx = dy = 0
            if now < self.shake_until and self.shake_strength > 0:
                dx = random.randint(-self.shake_strength, self.shake_strength)
                dy = random.randint(-self.shake_strength, self.shake_strength)

            # 3. 그리기
            if pix:
                painter.drawPixmap(dx, dy + self.char_y, pix)

                # 4. 말풍선 그리기 (높이 수정본 유지)
                if self.say_text and now < self.say_until:
                    font = QFont("온글잎 박다현체", 13)
                    font.setBold(True)
                    painter.setFont(font)
                    bw = self.bubble.width() if self.bubble else 160
                    bh = self.bubble.height() if self.bubble else 50
                    bx = (self.width() - bw) // 2
                    by = max(0, self.char_y - bh + 100) # 가깝게 조정된 수치
                    bubble_rect = QRect(bx, by, bw, bh)

                    if self.bubble: painter.drawPixmap(bx, by, self.bubble)
                    else:
                        painter.setOpacity(0.9); painter.setBrush(Qt.white); painter.setPen(Qt.NoPen)
                        painter.drawRoundedRect(bubble_rect, 10, 10); painter.setOpacity(1.0)

                    painter.setPen(Qt.black)
                    l, t, r, b = (12, 8, 12, 8) 
                    text_rect = bubble_rect.adjusted(l, t, -r, -b)
                    painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.say_text)

            elif self.say_text and now >= self.say_until: self.say_text = ""

        finally:
            painter.end()

