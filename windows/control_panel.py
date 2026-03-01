"""
windows/control_panel.py - 메인 컨트롤 패널 (상태 + 버튼들 + 로그)
- 프레임리스(커스텀 프레임/타이틀바)
- 테마 시스템: asset/ui/theme/{pink,dark}
- 아이콘 분리: asset/ui/icon
- 채팅(입력창, 전송버튼) 제거됨
- 이름변경 버튼: 아이콘 버튼으로 변경
- 기분 옆: 테마 변경 아이콘 버튼 추가
"""

import random
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer, QPoint
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import app_icon_DIR
from utils.helpers import trigger_pet_action_bubble
from state import PetState, clamp
from windows.name_window import NameWindow
from windows.house_window import HouseWindow
from windows.job_window import JobWindow
from windows.shop_window import ShopWindow
from windows.study_window import StudyWindow


# -------------------------
# Asset / Theme helpers
# -------------------------
def _project_root() -> Path:
    # windows/control_panel.py 기준: project_root/windows/control_panel.py
    return Path(__file__).resolve().parents[1]


ASSET_UI_DIR = _project_root() / "asset" / "ui"
ICON_DIR = ASSET_UI_DIR / "icon"
THEME_DIR = ASSET_UI_DIR / "theme"


def _p(p: Path) -> str:
    # QSS에서 쓰기 좋게 file url 형태로
    return p.as_posix().replace("\\", "/")


def _exists(p: Path) -> bool:
    try:
        return p.exists()
    except Exception:
        return False


# -------------------------
# Custom TitleBar (frameless drag region)
# -------------------------
class TitleBar(QWidget):
    """
    window_titlebar.png 를 배경으로 쓰는 커스텀 타이틀바.
    - 드래그 이동 지원
    - 최소화/닫기 버튼
    """

    def __init__(self, parent_panel: "ControlPanel"):
        super().__init__(parent_panel)
        self.panel = parent_panel
        self.setObjectName("TitleBar")
        self.setFixedHeight(48)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        self.title_label = QLabel("라이미")
        self.title_label.setObjectName("TitleLabel")
        lay.addWidget(self.title_label)

        lay.addStretch(1)

        # 최소화 버튼(선택)
        self.min_btn = QPushButton("")
        self.min_btn.setObjectName("MinButton")
        self.min_btn.setFixedSize(32, 32)
        self.min_btn.clicked.connect(self.panel.showMinimized)
        lay.addWidget(self.min_btn)

        # 닫기 버튼
        self.close_btn = QPushButton("")
        self.close_btn.setObjectName("CloseButton")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.clicked.connect(self.panel.close)
        lay.addWidget(self.close_btn)

        self._dragging = False
        self._drag_offset = QPoint(0, 0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = e.globalPosition().toPoint() - self.panel.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._dragging:
            self.panel.move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._dragging = False
        super().mouseReleaseEvent(e)


# -------------------------
# Main Control Panel
# -------------------------
class ControlPanel(QWidget):
    def __init__(
        self,
        state: PetState,
        pet,
        app_icon: Optional[QIcon] = None,
        default_theme: str = "pink",  # "pink" or "dark"
    ):
        super().__init__()
        self.state = state
        self.pet = pet

        # theme state
        self.theme = default_theme if default_theme in ("pink", "dark") else "pink"

        # frameless window
        self.setWindowTitle(f"{state.pet_name} - Control Panel")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # size fixed
        self.setFixedSize(400, 600)

        if app_icon:
            self.setWindowIcon(app_icon)

        # ---- Outer frame container (painted via QSS border-image)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.frame = QWidget(self)
        self.frame.setObjectName("WindowFrame")
        outer.addWidget(self.frame)

        root = QVBoxLayout(self.frame)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # TitleBar
        self.titlebar = TitleBar(self)
        root.addWidget(self.titlebar)

        # Header row (money / name / rename / mood / theme)
        header = QHBoxLayout()
        header.setSpacing(8)

        self.money_label = QLabel("")
        self.money_label.setObjectName("MoneyLabel")
        header.addWidget(self.money_label)

        header.addSpacing(6)

        self.name_label = QLabel("")
        self.name_label.setObjectName("NameLabel")
        header.addWidget(self.name_label)

        # rename icon button (텍스트 제거)
        self.rename_btn = QPushButton("")
        self.rename_btn.setObjectName("RenameIconButton")
        self.rename_btn.setFixedSize(32, 32)
        self.rename_btn.clicked.connect(self.open_name_change)
        header.addWidget(self.rename_btn)

        header.addStretch(1)

        self.mood_label = QLabel("")
        self.mood_label.setObjectName("MoodLabel")
        header.addWidget(self.mood_label)

        # theme toggle button (기분 옆)
        self.theme_btn = QPushButton("")
        self.theme_btn.setObjectName("ThemeIconButton")
        self.theme_btn.setFixedSize(32, 32)
        self.theme_btn.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_btn)

        root.addLayout(header)

        # chat log (read-only)
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setObjectName("ChatLog")
        self.chat_log.setMinimumHeight(220)
        root.addWidget(self.chat_log, 1)

        # status bars (2x2가 UX상 더 예쁨)
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

        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(12)
        status_grid.setVerticalSpacing(8)
        status_grid.addWidget(self.fun_bar, 0, 0)
        status_grid.addWidget(self.mood_bar, 0, 1)
        status_grid.addWidget(self.hunger_bar, 1, 0)
        status_grid.addWidget(self.energy_bar, 1, 1)
        root.addLayout(status_grid)

        # action buttons (3x2)
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

        # 기존 메뉴 아이콘(기존 asset 경로 유지)
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

        self.key_hint = QLabel("ESC=종료")
        self.key_hint.setObjectName("KeyHint")
        root.addWidget(self.key_hint)

        # sub windows
        self.name_window = NameWindow(self.state, app_icon=app_icon)
        self.house_win = HouseWindow(self.state, self.pet, app_icon=app_icon)
        self.job_win = JobWindow(self.state, app_icon=app_icon)
        self.shop_win = ShopWindow(self.state, app_icon=app_icon)
        self.study_win = StudyWindow(self.state, shop_win=self.shop_win, app_icon=app_icon)

        # apply theme + icons
        self.apply_theme(self.theme)

        self._sync_ui()
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._sync_ui)
        self.ui_timer.start(250)

    # -------------------------
    # Theme
    # -------------------------
    def theme_path(self, filename: str) -> Path:
        return THEME_DIR / self.theme / filename

    def icon_path(self, filename: str) -> Path:
        return ICON_DIR / filename

    def apply_theme(self, theme_name: str):
        if theme_name not in ("pink", "dark"):
            theme_name = "pink"
        self.theme = theme_name

        # load theme images
        window_frame = self.theme_path("window_frame.png")
        titlebar_bg = self.theme_path("window_titlebar.png")

        btn_close_n = self.theme_path("btn_close_normal.png")
        btn_close_h = self.theme_path("btn_close_hover.png")
        btn_close_p = self.theme_path("btn_close_pressed.png")

        btn_min_n = self.theme_path("btn_min_normal.png")
        btn_min_h = self.theme_path("btn_min_hover.png")
        btn_min_p = self.theme_path("btn_min_pressed.png")

        btn_m = self.theme_path("btn_m.png")
        btn_l = self.theme_path("btn_l.png")

        panel_header = self.theme_path("panel_header.png")
        panel_chat = self.theme_path("panel_chat.png")
        panel_status = self.theme_path("panel_status.png")

        bar_track = self.theme_path("bar_track.png")
        speech_bubble = self.theme_path("speech_bubble.png")  # (다른 창/말풍선에서도 쓸 수 있음)

        # icons
        ic_close = self.icon_path("ic_close.png")
        ic_min = self.icon_path("ic_min.png")
        ic_rename = self.icon_path("ic_rename.png")
        ic_theme = self.icon_path("ic_theme.png")

        # icons set (fallback: text)
        if _exists(ic_close):
            self.titlebar.close_btn.setIcon(QIcon(str(ic_close)))
            self.titlebar.close_btn.setIconSize(QSize(18, 18))
        else:
            self.titlebar.close_btn.setText("X")

        if _exists(ic_min):
            self.titlebar.min_btn.setIcon(QIcon(str(ic_min)))
            self.titlebar.min_btn.setIconSize(QSize(18, 18))
        else:
            self.titlebar.min_btn.setText("—")

        if _exists(ic_rename):
            self.rename_btn.setIcon(QIcon(str(ic_rename)))
            self.rename_btn.setIconSize(QSize(18, 18))
        else:
            self.rename_btn.setText("✎")

        if _exists(ic_theme):
            self.theme_btn.setIcon(QIcon(str(ic_theme)))
            self.theme_btn.setIconSize(QSize(18, 18))
        else:
            self.theme_btn.setText("🎨")

        # QSS
        # NOTE: border-image inset은 너가 만든 에셋 기준으로 조정 가능.
        qss = f"""
        QWidget#WindowFrame {{
            border-image: url({_p(window_frame)}) 24 24 24 24 stretch stretch;
        }}

        QWidget#TitleBar {{
            border-image: url({_p(titlebar_bg)}) 16 16 16 16 stretch stretch;
        }}

        QLabel#TitleLabel {{
            background: transparent;
            font-weight: 700;
        }}

        QPushButton#CloseButton, QPushButton#MinButton {{
            border: none;
            background: transparent;
        }}

        /* close/min buttons with themed background */
        QPushButton#CloseButton {{
            border-image: url({_p(btn_close_n)}) 12 12 12 12 stretch stretch;
        }}
        QPushButton#CloseButton:hover {{
            border-image: url({_p(btn_close_h)}) 12 12 12 12 stretch stretch;
        }}
        QPushButton#CloseButton:pressed {{
            border-image: url({_p(btn_close_p)}) 12 12 12 12 stretch stretch;
        }}

        QPushButton#MinButton {{
            border-image: url({_p(btn_min_n)}) 12 12 12 12 stretch stretch;
        }}
        QPushButton#MinButton:hover {{
            border-image: url({_p(btn_min_h)}) 12 12 12 12 stretch stretch;
        }}
        QPushButton#MinButton:pressed {{
            border-image: url({_p(btn_min_p)}) 12 12 12 12 stretch stretch;
        }}

        /* header labels */
        QLabel#MoneyLabel, QLabel#NameLabel, QLabel#MoodLabel {{
            padding: 6px 10px;
        }}

        /* rename/theme icon buttons */
        QPushButton#RenameIconButton, QPushButton#ThemeIconButton {{
            border: none;
            background: transparent;
            min-width: 32px;
            min-height: 32px;
        }}

        /* chat panel */
        QTextEdit#ChatLog {{
            border-image: url({_p(panel_chat)}) 16 16 16 16 stretch stretch;
            padding: 10px;
        }}

        /* progress bars: track + chunk */
        QProgressBar {{
            border-image: url({_p(bar_track)}) 14 14 14 14 stretch stretch;
            text-align: center;
            font-weight: 700;
        }}
        QProgressBar::chunk {{
            /* theme별 fill이 아직 없어서 기본은 단색.
               나중에 bar_fill_*.png 만들어서 여기 url로 바꾸면 됨 */
            background: rgba(255, 255, 255, 90);
            margin: 6px;
        }}

        /* menu buttons */
        QPushButton#MenuButton {{
            border-image: url({_p(btn_m)}) 14 14 14 14 stretch stretch;
            padding: 6px 10px;
            font-weight: 700;
        }}
        QPushButton#MenuButton:pressed {{
            border-image: url({_p(btn_l)}) 14 14 14 14 stretch stretch; /* 눌림을 큰버튼으로 대체(임시) */
        }}

        QLabel#KeyHint {{
            background: transparent;
            padding: 2px 4px;
        }}
        """

        self.setStyleSheet(qss)

    def toggle_theme(self):
        self.apply_theme("dark" if self.theme == "pink" else "pink")

    # -------------------------
    # UI helpers
    # -------------------------
    def _try_set_icon(self, btn: QPushButton, path):
        try:
            p = Path(path)
            if p.exists():
                btn.setIcon(QIcon(str(p)))
                btn.setIconSize(QSize(22, 22))
        except Exception:
            pass

    def _sync_ui(self):
        self.money_label.setText(f"{int(self.state.money)}")
        self.name_label.setText(f"{self.state.pet_name}")
        self.mood_label.setText(f"{self.state.mood_label}")

        self.fun_bar.setValue(int(self.state.fun))
        self.mood_bar.setValue(int(self.state.mood))
        self.hunger_bar.setValue(int(self.state.hunger))
        self.energy_bar.setValue(int(self.state.energy))

        self.setWindowTitle(f"{self.state.pet_name} - Control Panel")
        self.titlebar.title_label.setText(f"{self.state.pet_name} - Panel")

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
            e.accept()
            return
        super().keyPressEvent(e)

    # -------------------------
    # Button actions
    # -------------------------
    def feed_pet(self):
        self.state.hunger = clamp(self.state.hunger + 12)
        self.state.mood = clamp(self.state.mood + 1)
        self._append_log("🍚 밥을 줬다!")

        msg = random.choice(["냠냠! 맛있어!", "배부르다 찍!", "밥 최고!"])
        self._append_log(f"{self.state.pet_name}: {msg}")

        target = self._active_pet_for_chat()
        if hasattr(target, "trigger_eat_visual"):
            target.trigger_eat_visual()

        trigger_pet_action_bubble(target, self.chat_log, [msg])

    def pet_pet(self):
        self.state.mood = clamp(self.state.mood + 3)
        self.state.fun = clamp(self.state.fun + 1)
        self._append_log("💗 쓰다듬었다!")

        msg = random.choice(["헤헤 기분 좋아 💗", "더 쓰다듬어줘!", "따뜻해..."])
        self._append_log(f"{self.state.pet_name}: {msg}")

        target = self._active_pet_for_chat()
        if hasattr(target, "start_shake"):
            target.start_shake(sec=0.4, strength=2)

        trigger_pet_action_bubble(target, self.chat_log, [msg])

    def play_pet(self):
        target = self._active_pet_for_chat()

        if self.state.energy < 4:
            self._append_log("😴 에너지가 부족해서 못 놀겠어…")
            msg = random.choice(["너무 졸려... 나중에 놀자...", "힘들어 헉헉..."])
            self._append_log(f"{self.state.pet_name}: {msg}")

            if hasattr(target, "start_sleep_for_60s"):
                target.start_sleep_for_60s()

            trigger_pet_action_bubble(target, self.chat_log, [msg])
            return

        self.state.energy = clamp(self.state.energy - 4, 0.0, self.state.max_energy)
        self.state.fun = clamp(self.state.fun + 6)
        self.state.mood = clamp(self.state.mood + 1)
        self._append_log("🎮 같이 놀았다!")

        msg = random.choice(["야호! 재밌다!", "우다다다!", "한 번 더 놀자!"])
        self._append_log(f"{self.state.pet_name}: {msg}")

        if hasattr(target, "do_jump"):
            target.do_jump(strength=14)

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