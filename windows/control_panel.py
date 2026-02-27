"""
windows/control_panel.py - 메인 컨트롤 패널 (채팅 + 상태 + 버튼들)
"""
from typing import Optional

from PySide6.QtCore import QEvent, Qt, QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from config import app_icon_DIR
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

        self.setWindowTitle(f"{state.pet_name} - Chat Panel")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
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

        # 채팅 로그
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setObjectName("ChatLog")
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

        # 입력창 + 전송
        input_row = QHBoxLayout()
        self.input = QTextEdit()
        self.input.setObjectName("ChatInput")
        self.input.setFixedHeight(72)
        self.input.installEventFilter(self)

        self.send_btn = QPushButton("전송")
        self.send_btn.setObjectName("SendButton")
        self.send_btn.setFixedSize(92, 72)
        self.send_btn.clicked.connect(self.on_send)

        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_btn)
        root.addLayout(input_row)

        self.key_hint = QLabel("Enter=전송 / Shift+Enter=줄바꿈 / 드래그=이동 / ESC=종료")
        self.key_hint.setObjectName("KeyHint")
        root.addWidget(self.key_hint)

        # 서브 창들
        self.name_window = NameWindow(self.state, app_icon=app_icon)

        self.house_win = HouseWindow(self.state, self.pet, app_icon=app_icon)

        # ✅ 여기서 핵심: JobWindow는 icon이 아니라 app_icon을 받음
        self.job_win = JobWindow(self.state, app_icon=app_icon)

        # 소모품 상점(StudyWindow에서 열 것)
        self.shop_win = ShopWindow(self.state, app_icon=app_icon)

        # StudyWindow에 shop_win 주입(같은 창 공유)
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

        self.setWindowTitle(f"{self.state.pet_name} - Chat Panel")

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self.on_send()
                return True
            if event.key() == Qt.Key_Escape:
                QApplication.quit()
                return True
        return super().eventFilter(obj, event)

    # -------------------------
    # 버튼 동작
    # -------------------------
    def feed_pet(self):
        self.state.hunger = clamp(self.state.hunger + 12)
        self.state.mood = clamp(self.state.mood + 1)
        self._append_log("🍚 밥을 줬다!")

    def pet_pet(self):
        self.state.mood = clamp(self.state.mood + 3)
        self.state.fun = clamp(self.state.fun + 1)
        self._append_log("💗 쓰다듬었다!")

    def play_pet(self):
        if self.state.energy < 4:
            self._append_log("😴 에너지가 부족해서 못 놀겠어…")
            return
        self.state.energy = clamp(self.state.energy - 4, 0.0, self.state.max_energy)
        self.state.fun = clamp(self.state.fun + 6)
        self.state.mood = clamp(self.state.mood + 1)
        self._append_log("🎮 같이 놀았다!")

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
        # ✅ 집 창이 열려있으면 집 안 펫에게 대화 라우팅
        try:
            if self.house_win.isVisible():
                return self.house_win.house_pet
        except Exception:
            pass
        return self.pet

    def on_send(self):
        msg = (self.input.toPlainText() or "").strip()
        if not msg:
            return

        self._append_log(f"나: {msg}")
        self.input.clear()

        target = self._active_pet_for_chat()
        try:
            if hasattr(target, "send_chat_from_panel"):
                target.send_chat_from_panel(msg, self.chat_log)
            else:
                self.chat_log.append("[오류] 펫 객체에 send_chat_from_panel이 없어.")
        except Exception as ex:
            self.chat_log.append(f"[오류] 대화 처리 실패: {ex}")