"""
windows/control_panel.py - 메인 컨트롤 패널 (상태 + 버튼들 + 로그)
- 채팅(입력창, 전송버튼) 제거됨
- 로그 창 높이 확장 (UX 개선)
"""
import random
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from config import app_icon_DIR
from utils.helpers import trigger_pet_action_bubble
from state import PetState, clamp
from windows.name_window import NameWindow
from windows.house_window import HouseWindow
from windows.job_window import JobWindow
from windows.shop_window import ShopWindow
from windows.study_window import StudyWindow


class ControlPanel(QWidget):
    def __init__(
        self,
        state: PetState,
        pet,
        app_icon: Optional[QIcon] = None,
    ):
        super().__init__()
        self.state = state
        self.pet = pet

        self.setWindowTitle(f"{state.pet_name} - Control Panel")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        # ✅ 크기 고정
        self.setFixedSize(400, 600)

        if app_icon:
            self.setWindowIcon(app_icon)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # 상단 헤더
        header = QHBoxLayout()
        header.setSpacing(10)

        self.money_label = QLabel("")
        self.money_label.setObjectName("MoneyLabel")
        header.addWidget(self.money_label)

        header.addSpacing(8)

        self.name_label = QLabel("")
        self.name_label.setObjectName("NameLabel")
        header.addWidget(self.name_label)

        self.rename_btn = QPushButton("이름변경")
        self.rename_btn.setObjectName("GhostButton")
        self.rename_btn.clicked.connect(self.open_name_change)
        header.addWidget(self.rename_btn)

        header.addStretch(1)

        self.mood_label = QLabel("")
        self.mood_label.setObjectName("MoodLabel")
        header.addWidget(self.mood_label)

        root.addLayout(header)

        # 상태 로그 (채팅 입력창 제거 후 높이 확장)
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setObjectName("ChatLog")
        self.chat_log.setMinimumHeight(300)  # ✅ 최소 높이 300 보장
        root.addWidget(self.chat_log, 1)

        # 스테이터스 바
        self.fun_bar = QProgressBar()
        self.fun_bar.setObjectName("BarFun")
        self.fun_bar.setRange(0, 100)
        self.fun_bar.setFormat("재미 %p%")
        self.fun_bar.setTextVisible(True)

        self.mood_bar = QProgressBar()
        self.mood_bar.setObjectName("BarMood")
        self.mood_bar.setRange(0, 100)
        self.mood_bar.setFormat("기분 %p%")
        self.mood_bar.setTextVisible(True)

        self.hunger_bar = QProgressBar()
        self.hunger_bar.setObjectName("BarHunger")
        self.hunger_bar.setRange(0, 100)
        self.hunger_bar.setFormat("배고픔 %p%")
        self.hunger_bar.setTextVisible(True)

        self.energy_bar = QProgressBar()
        self.energy_bar.setObjectName("BarEnergy")
        self.energy_bar.setRange(0, 100)
        self.energy_bar.setFormat("에너지 %p%")
        self.energy_bar.setTextVisible(True)

        for bar in (self.fun_bar, self.mood_bar, self.hunger_bar, self.energy_bar):
            root.addWidget(bar)

        # 액션 버튼 (3x2)
        btn_grid = QGridLayout()
        btn_grid.setHorizontalSpacing(10)
        btn_grid.setVerticalSpacing(10)

        self.feed_btn = QPushButton("밥주기")
        self.feed_btn.clicked.connect(self.feed_pet)

        self.pet_btn = QPushButton("쓰다듬기")
        self.pet_btn.clicked.connect(self.pet_pet)

        self.play_btn = QPushButton("놀아주기")
        self.play_btn.clicked.connect(self.play_pet)

        self.home_btn = QPushButton("집")
        self.home_btn.clicked.connect(self.open_home)

        self.job_btn = QPushButton("아르바이트")
        self.job_btn.clicked.connect(self.open_job)

        self.study_btn = QPushButton("공부")
        self.study_btn.clicked.connect(self.open_study)

        for b in (self.feed_btn, self.pet_btn, self.play_btn, self.home_btn, self.job_btn, self.study_btn):
            b.setMinimumHeight(46)
            b.setObjectName("MenuButton")

        self._try_set_icon(self.feed_btn, app_icon_DIR / "feed.png")
        self._try_set_icon(self.pet_btn, app_icon_DIR / "pet.png")
        self._try_set_icon(self.play_btn, app_icon_DIR / "play.png")
        self._try_set_icon(self.home_btn, app_icon_DIR / "home.png")
        self._try_set_icon(self.job_btn, app_icon_DIR / "job.png")
        self._try_set_icon(self.study_btn, app_icon_DIR / "study.png")

        btn_grid.addWidget(self.feed_btn, 0, 0)
        btn_grid.addWidget(self.pet_btn, 0, 1)
        btn_grid.addWidget(self.play_btn, 0, 2)
        btn_grid.addWidget(self.home_btn, 1, 0)
        btn_grid.addWidget(self.job_btn, 1, 1)
        btn_grid.addWidget(self.study_btn, 1, 2)
        root.addLayout(btn_grid)

        # ❌ 입력창(QTextEdit)과 전송 버튼(QPushButton) 삭제됨
        # ❌ 관련 EventFilter(엔터키 전송 등) 삭제됨

        self.key_hint = QLabel("ESC=종료")
        self.key_hint.setObjectName("KeyHint")
        root.addWidget(self.key_hint)

        # 서브 창들
        self.name_window = NameWindow(self.state, app_icon=app_icon)
        self.house_win = HouseWindow(self.state, self.pet, app_icon=app_icon)
        self.job_win = JobWindow(self.state, app_icon=app_icon)
        self.shop_win = ShopWindow(self.state, app_icon=app_icon)
        self.study_win = StudyWindow(self.state, shop_win=self.shop_win, app_icon=app_icon)

        self._sync_ui()
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._sync_ui)
        self.ui_timer.start(250)

    def _try_set_icon(self, btn: QPushButton, path):
        try:
            from pathlib import Path
            p = Path(path)
            if p.exists():
                btn.setIcon(QIcon(str(p)))
                btn.setIconSize(QSize(22, 22))
        except Exception:
            pass

    def _sync_ui(self):
        self.money_label.setText(f"소지금 {int(self.state.money)}")
        self.name_label.setText(f"이름 {self.state.pet_name}")
        self.mood_label.setText(f"기분 {self.state.mood_label}")

        self.fun_bar.setValue(int(self.state.fun))
        self.mood_bar.setValue(int(self.state.mood))
        self.hunger_bar.setValue(int(self.state.hunger))
        self.energy_bar.setValue(int(self.state.energy))

        self.setWindowTitle(f"{self.state.pet_name} - Control Panel")

    # -------------------------
    # 버튼 동작
    # -------------------------
    def feed_pet(self):
        self.state.hunger = clamp(self.state.hunger + 12)
        self.state.mood = clamp(self.state.mood + 1)
        self._append_log("🍚 밥을 줬다!")
        
        msg = random.choice(["냠냠! 맛있어!", "배부르다 찍!", "밥 최고!"])
        self._append_log(f"{self.state.pet_name}: {msg}")
        
        target = self._active_pet_for_chat()
        if hasattr(target, "trigger_eat_visual"):
            target.trigger_eat_visual() # ✅ 먹는 모션 실행
            
        trigger_pet_action_bubble(target, self.chat_log, [msg])

    def pet_pet(self):
        self.state.mood = clamp(self.state.mood + 3)
        self.state.fun = clamp(self.state.fun + 1)
        self._append_log("💗 쓰다듬었다!")

        msg = random.choice(["헤헤 기분 좋아 💗", "더 쓰다듬어줘!", "따뜻해..."])
        self._append_log(f"{self.state.pet_name}: {msg}")

        target = self._active_pet_for_chat()
        if hasattr(target, "start_shake"):
            target.start_shake(sec=0.4, strength=2) # ✅ 기분 좋아서 흔들림
            
        trigger_pet_action_bubble(target, self.chat_log, [msg])

    def play_pet(self):
        target = self._active_pet_for_chat()
        
        if self.state.energy < 4:
            self._append_log("😴 에너지가 부족해서 못 놀겠어…")
            msg = random.choice(["너무 졸려... 나중에 놀자...", "힘들어 헉헉..."])
            self._append_log(f"{self.state.pet_name}: {msg}")
            
            if hasattr(target, "start_sleep_for_60s"):
                target.start_sleep_for_60s() # ✅ 에너지 없으면 자는 모션 실행
                
            trigger_pet_action_bubble(target, self.chat_log, [msg])
            return
            
        self.state.energy = clamp(self.state.energy - 4, 0.0, self.state.max_energy)
        self.state.fun = clamp(self.state.fun + 6)
        self.state.mood = clamp(self.state.mood + 1)
        self._append_log("🎮 같이 놀았다!")
        
        msg = random.choice(["야호! 재밌다!", "우다다다!", "한 번 더 놀자!"])
        self._append_log(f"{self.state.pet_name}: {msg}")

        if hasattr(target, "do_jump"):
            target.do_jump(strength=14) # ✅ 신나서 점프 모션
            
        trigger_pet_action_bubble(target, self.chat_log, [msg])

    def open_home(self):
        self.house_win.show()
        self.house_win.raise_()
        self.house_win.activateWindow()

    def open_job(self):
        self.job_win.show()
        self.job_win.raise_()
        self.job_win.activateWindow()

    def open_study(self):
        self.study_win.show()
        self.study_win.raise_()
        self.study_win.activateWindow()

    def open_name_change(self):
        self.name_window.show()
        self.name_window.raise_()
        self.name_window.activateWindow()

    def _append_log(self, msg: str):
        self.chat_log.append(msg)

    def _active_pet_for_chat(self):
        try:
            if self.house_win.isVisible():
                return self.house_win.house_pet
        except Exception:
            pass
        return self.pet