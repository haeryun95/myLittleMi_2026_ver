"""
windows/house_window.py - 집 창 + 집 안 펫 위젯
"""
import random
import time
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QPushButton, QWidget

from config import (
    ANIM_DIR, ANIM_SPEED_MS, BG_CATEGORIES, BG_DEFAULT_PATH, BG_LAYER_ORDER,
    BUBBLE_PATH, EAT_SHAKE_DURATION, EAT_SHAKE_STRENGTH, FACE_HOLD_SEC,
    HOUSE_BUBBLE_PADDING, HOUSE_SCALE_BUBBLE, HOUSE_SCALE_CHAR,
    HOUSE_WIN_H, HOUSE_WIN_W, SLEEP_DURATION_SEC, SLEEP_RECOVER_ENERGY,
)
from state import PetState, clamp
from utils.image_loader import load_folder_pixmaps_as_map, load_folder_pixmaps_as_list, make_flipped_frames
from utils.json_utils import get_catalog, resolve_bg_path
from ui.placement_panel import PlacementPanel


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
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
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
        self.walk_frames_flipped = make_flipped_frames(self.walk_frames) if self.walk_frames else []

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
        if self.sleeping or self.mode != "normal":
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
            self.vy = 0

        self.move(int(x), int(y))
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)

            if self.mode == "walk" and self.walk_frames:
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


class HouseWindow(QWidget):
    def __init__(self, state: PetState, desktop_pet, app_icon: Optional[QIcon] = None):
        super().__init__()
        self.state = state
        self.pet = desktop_pet

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
        self._reposition_overlay_ui()
        self.placement_btn.clicked.connect(self.open_placement_panel)

        self.placement_panel: Optional[PlacementPanel] = None
        self.house_pet = HousePetWidget(self.state, parent=self)
        self.house_pet.raise_()
        self.pet.hide()

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
            self.default_bg = QPixmap(str(BG_DEFAULT_PATH)).scaled(
                self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            )
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
            self.pet.show()
            self.pet.raise_()
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
