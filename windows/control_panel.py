"""
windows/control_panel.py - 메인 컨트롤 패널
- 프레임리스(커스텀 프레임/타이틀바)
- 테마: asset/ui/theme/{pink,dark}
- 아이콘: asset/ui/icon
- 채팅 입력창/전송버튼 제거됨(로그만)
- 이름변경 버튼: 아이콘 버튼
- 기분 옆: 테마 변경 아이콘 버튼
- 최소화: 시스템 트레이로 숨김 (바탕화면 펫은 유지)
- 닫기: 전체 프로그램 종료
"""

import random
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer, QPoint
from PySide6.QtGui import QIcon, QAction, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMenu,
    QSystemTrayIcon,
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
# Asset helpers
# -------------------------
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


ASSET_UI_DIR = _project_root() / "asset" / "ui"
ICON_DIR = ASSET_UI_DIR / "icon"
THEME_DIR = ASSET_UI_DIR / "theme"


def _p(p: Path) -> str:
    return p.as_posix().replace("\\", "/")


def _exists(p: Path) -> bool:
    try:
        return p.exists()
    except Exception:
        return False


# -------------------------
# TitleBar (frameless drag)
# -------------------------
class TitleBar(QWidget):
    def __init__(self, frame_parent: QWidget, panel: "ControlPanel"):
        super().__init__(frame_parent)
        self.panel = panel
        self.setObjectName("TitleBar")
        self.setFixedHeight(48)
        
        self.setAttribute(Qt.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        self.title_label = QLabel("라이미 - Panel")
        self.title_label.setObjectName("TitleLabel")
        lay.addWidget(self.title_label)

        lay.addStretch(1)

        self.min_btn = QPushButton("")
        self.min_btn.setObjectName("MinButton")
        self.min_btn.setFixedSize(32, 32)
        self.min_btn.clicked.connect(self.panel.minimize_to_tray)
        lay.addWidget(self.min_btn)

        self.close_btn = QPushButton("")
        self.close_btn.setObjectName("CloseButton")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.clicked.connect(self.panel.quit_app)
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
        default_theme: str = "pink",
    ):
        super().__init__()
        self.state = state
        self.pet = pet
        self.theme = default_theme if default_theme in ("pink", "dark") else "pink"

        QApplication.instance().setQuitOnLastWindowClosed(False)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.setFixedSize(400, 600)
        self.setWindowTitle(f"{state.pet_name} - Control Panel")

        if app_icon:
            self.setWindowIcon(app_icon)

        self.tray: Optional[QSystemTrayIcon] = None
        self._init_tray(app_icon)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.frame = QWidget(self)
        self.frame.setObjectName("WindowFrame")
        self.frame.setAttribute(Qt.WA_StyledBackground, True)
        outer.addWidget(self.frame)

        frame_lay = QVBoxLayout(self.frame)
        frame_lay.setContentsMargins(0, 0, 0, 0)
        frame_lay.setSpacing(0)

        # 1. 최상단 타이틀 바
        self.titlebar = TitleBar(self.frame, self)
        frame_lay.addWidget(self.titlebar)

        # 2. 내부 콘텐츠 영역
        content_widget = QWidget()
        root = QVBoxLayout(content_widget)
        root.setContentsMargins(24, 12, 24, 24)
        root.setSpacing(10)
        frame_lay.addWidget(content_widget)

        # ✅ 헤더 재배치: 소지금 아이콘 | 소지금 | 이름 | 변경버튼 | 기분 | 테마버튼
        header = QHBoxLayout()
        header.setSpacing(8)

        self.money_icon = QLabel()
        self.money_icon.setFixedSize(20, 20)
        self.money_icon.setScaledContents(True)
        header.addWidget(self.money_icon)

        self.money_label = QLabel("")
        self.money_label.setObjectName("MoneyLabel")
        header.addWidget(self.money_label)

        header.addSpacing(10)

        self.name_label = QLabel("")
        self.name_label.setObjectName("NameLabel")
        header.addWidget(self.name_label)

        self.rename_btn = QPushButton("")
        self.rename_btn.setObjectName("RenameIconButton")
        self.rename_btn.setFixedSize(28, 28)
        self.rename_btn.clicked.connect(self.open_name_change)
        header.addWidget(self.rename_btn)

        header.addStretch(1)

        self.mood_label = QLabel("")
        self.mood_label.setObjectName("MoodLabel")
        header.addWidget(self.mood_label)

        self.theme_btn = QPushButton("")
        self.theme_btn.setObjectName("ThemeIconButton")
        self.theme_btn.setFixedSize(28, 28)
        self.theme_btn.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_btn)

        root.addLayout(header)

        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setObjectName("ChatLog")
        self.chat_log.setMinimumHeight(160)
        root.addWidget(self.chat_log, 1)

        self.fun_bar = self._make_bar("BarFun", "재미 %p%")
        self.mood_bar = self._make_bar("BarMood", "기분 %p%")
        self.hunger_bar = self._make_bar("BarHunger", "배고픔 %p%")
        self.energy_bar = self._make_bar("BarEnergy", "에너지 %p%")

        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(12)
        status_grid.setVerticalSpacing(8)
        status_grid.addWidget(self.fun_bar, 0, 0)
        status_grid.addWidget(self.mood_bar, 0, 1)
        status_grid.addWidget(self.hunger_bar, 1, 0)
        status_grid.addWidget(self.energy_bar, 1, 1)
        root.addLayout(status_grid)

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

        self._try_set_menu_icon(self.feed_btn, app_icon_DIR / "feed.png")
        self._try_set_menu_icon(self.pet_btn, app_icon_DIR / "pet.png")
        self._try_set_menu_icon(self.play_btn, app_icon_DIR / "play.png")
        self._try_set_menu_icon(self.home_btn, app_icon_DIR / "home.png")
        self._try_set_menu_icon(self.job_btn, app_icon_DIR / "job.png")
        self._try_set_menu_icon(self.study_btn, app_icon_DIR / "study.png")

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

        self.name_window: Optional[NameWindow] = None
        self.house_win = HouseWindow(self.state, self.pet, app_icon=app_icon)
        self.job_win = JobWindow(self.state, app_icon=app_icon)
        self.shop_win = ShopWindow(self.state, app_icon=app_icon)
        self.study_win = StudyWindow(self.state, shop_win=self.shop_win, app_icon=app_icon)

        self.apply_theme(self.theme)

        self._sync_ui()
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._sync_ui)
        self.ui_timer.start(250)

    # -------------------------
    # Tray / App quit
    # -------------------------
    def _init_tray(self, app_icon: Optional[QIcon]):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return

        icon = app_icon if app_icon else self.windowIcon()
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("MyLittleMi")

        menu = QMenu()
        act_restore = QAction("열기", self)
        act_restore.triggered.connect(self.restore_from_tray)
        menu.addAction(act_restore)

        act_quit = QAction("종료", self)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.restore_from_tray()

    def minimize_to_tray(self):
        self.hide()
            
        try:
            self.house_win.hide()
            self.job_win.hide()
            self.study_win.hide()
            self.shop_win.hide()
            if self.name_window:
                self.name_window.hide()
        except Exception:
            pass

        if self.tray:
            self.tray.showMessage("라이미", "트레이로 숨겼어! (아이콘 클릭하면 다시 열려)", QSystemTrayIcon.Information, 1200)

    def restore_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        try:
            self.house_win.close()
            self.job_win.close()
            self.study_win.close()
            self.shop_win.close()
            if self.name_window:
                self.name_window.close()
            if self.pet:
                self.pet.close()
            if self.tray:
                self.tray.hide()
        except Exception:
            pass
        QApplication.instance().quit()

    def closeEvent(self, e):
        self.quit_app()
        e.accept()

    # -------------------------
    # Theme / Assets
    # -------------------------
    def theme_path(self, filename: str) -> Path:
        return THEME_DIR / self.theme / filename

    def icon_path(self, filename: str) -> Path:
        return ICON_DIR / filename

    def apply_theme(self, theme_name: str):
        if theme_name not in ("pink", "dark"):
            theme_name = "pink"
        self.theme = theme_name

        window_frame = self.theme_path("window_frame.png")

        btn_close_n = self.theme_path("btn_close_normal.png")
        btn_close_h = self.theme_path("btn_close_hover.png")
        btn_close_p = self.theme_path("btn_close_pressed.png")

        btn_min_n = self.theme_path("btn_min_normal.png")
        btn_min_h = self.theme_path("btn_min_hover.png")
        btn_min_p = self.theme_path("btn_min_pressed.png")

        btn_m = self.theme_path("btn_m.png")
        panel_chat = self.theme_path("panel_chat.png")
        bar_track = self.theme_path("bar_track.png")

        ic_rename = self.icon_path("ic_rename.png")
        ic_theme = self.icon_path("ic_theme.png")
        ic_coin = self.icon_path("ic_coin.png") # ✅ 코인 아이콘 추가

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
            
        if _exists(ic_coin):
            self.money_icon.setPixmap(QPixmap(str(ic_coin)))
        else:
            self.money_icon.setText("💰")
            self.money_icon.setAlignment(Qt.AlignCenter)

        text_color = "#ffffff" if self.theme == "dark" else "#333333"

        # ✅ slice 설정(24 24 24 24)을 0 0 0 0으로 바꿔서 원본 비율 강제 유지
        # ✅ TitleBar 배경을 투명하게 해서 겹침 현상 제거
        qss = f"""
        QWidget#WindowFrame {{
            background: transparent;
            border-image: url("{_p(window_frame)}") 0 0 0 0 stretch stretch;
        }}

        QWidget#TitleBar {{
            background: transparent;
        }}

        QLabel#TitleLabel {{
            background: transparent;
            font-weight: 800;
            color: {text_color};
        }}

        QPushButton#CloseButton, QPushButton#MinButton {{
            border: none;
            background: transparent;
        }}

        QPushButton#CloseButton {{
            image: url("{_p(btn_close_n)}");
        }}
        QPushButton#CloseButton:hover {{
            image: url("{_p(btn_close_h)}");
        }}
        QPushButton#CloseButton:pressed {{
            image: url("{_p(btn_close_p)}");
        }}

        QPushButton#MinButton {{
            image: url("{_p(btn_min_n)}");
        }}
        QPushButton#MinButton:hover {{
            image: url("{_p(btn_min_h)}");
        }}
        QPushButton#MinButton:pressed {{
            image: url("{_p(btn_min_p)}");
        }}

        QLabel#MoneyLabel, QLabel#NameLabel, QLabel#MoodLabel, QLabel {{
            background: transparent;
            font-weight: 700;
            color: {text_color};
        }}

        QPushButton#RenameIconButton, QPushButton#ThemeIconButton {{
            border: none;
            background: transparent;
            min-width: 28px;
            min-height: 28px;
        }}

        QTextEdit#ChatLog {{
            background: transparent;
            border-image: url("{_p(panel_chat)}") 16 16 16 16 stretch stretch;
            padding: 10px;
            color: {text_color};
        }}

        QProgressBar {{
            background: transparent;
            border-image: url("{_p(bar_track)}") 14 14 14 14 stretch stretch;
            text-align: center;
            font-weight: 700;
            color: {text_color};
        }}
        QProgressBar::chunk {{
            background: rgba(255, 255, 255, 90);
            margin: 6px;
        }}

        QPushButton#MenuButton {{
            background: transparent;
            border-image: url("{_p(btn_m)}") 14 14 14 14 stretch stretch;
            padding: 6px 10px;
            font-weight: 800;
            color: {text_color};
        }}

        QLabel#KeyHint {{
            background: transparent;
            padding: 2px 4px;
            color: {text_color};
        }}
        """
        self.setStyleSheet(qss)

    def toggle_theme(self):
        next_theme = "dark" if self.theme == "pink" else "pink"
        self.apply_theme(next_theme)

    # -------------------------
    # UI helpers
    # -------------------------
    def _make_bar(self, obj_name: str, fmt: str) -> QProgressBar:
        bar = QProgressBar()
        bar.setObjectName(obj_name)
        bar.setRange(0, 100)
        bar.setFormat(fmt)
        bar.setTextVisible(True)
        return bar

    def _try_set_menu_icon(self, btn: QPushButton, path):
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
            self.quit_app()
            e.accept()
            return
        super().keyPressEvent(e)

    # -------------------------
    # Sub windows
    # -------------------------
    def open_name_change(self):
        try:
            if self.name_window is None:
                self.name_window = NameWindow(self.state, app_icon=self.windowIcon())
                self.name_window.setParent(self, Qt.Window)
            self.name_window.show()
            self.name_window.raise_()
            self.name_window.activateWindow()
        except Exception as ex:
            self.chat_log.append(f"[에러] 이름 변경 창 열기 실패: {ex}")

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

    # -------------------------
    # Actions
    # -------------------------
    def _append_log(self, msg: str):
        self.chat_log.append(msg)

    def _active_pet_for_chat(self):
        try:
            if self.house_win.isVisible():
                return self.house_win.house_pet
        except Exception:
            pass
        return self.pet

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