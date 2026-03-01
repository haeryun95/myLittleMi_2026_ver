import random
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer, QPoint
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QVBoxLayout, QWidget, QMenu, QSystemTrayIcon,
    QStyle, QStyleOption
)

from config import app_icon_DIR
from utils.helpers import trigger_pet_action_bubble
from state import PetState, clamp
from windows.name_window import NameWindow
from windows.house_window import HouseWindow
from windows.job_window import JobWindow
from windows.study_window import StudyWindow

# -------------------------
# Helpers
# -------------------------
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]

ASSET_UI_DIR = _project_root() / "asset" / "ui"
ICON_DIR = ASSET_UI_DIR / "icon"
THEME_DIR = ASSET_UI_DIR / "theme"

def _p(p: Path) -> str:
    return p.resolve().as_posix()

# -------------------------
# 1. 상위 클래스 정의
# -------------------------
class StyledWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)
        painter.end()

# -------------------------
# 2. 타이틀바
# -------------------------
class TitleBar(StyledWidget):
    def __init__(self, frame_parent: QWidget, panel: "ControlPanel"):
        super().__init__(frame_parent)
        self.panel = panel
        self.setObjectName("TitleBar")
        self.setFixedHeight(48)
        
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 16, 0)
        lay.setSpacing(8) 
        
        self.sys_icon = QLabel()
        self.sys_icon.setObjectName("SystemIcon")
        self.sys_icon.setFixedSize(24, 24)
        lay.addWidget(self.sys_icon)
        
        self.title_label = QLabel("라이미 - Panel")
        self.title_label.setObjectName("TitleLabel")
        lay.addWidget(self.title_label)
        
        lay.addStretch(1)
        
        self.set_btn = QPushButton(); self.set_btn.setObjectName("SettingButton")
        self.min_btn = QPushButton(); self.min_btn.setObjectName("MinButton")
        self.close_btn = QPushButton(); self.close_btn.setObjectName("CloseButton")
        
        for btn, slot in [(self.set_btn, self.panel.open_settings), 
                          (self.min_btn, self.panel.minimize_to_tray), 
                          (self.close_btn, self.panel.quit_app)]:
            btn.setFixedSize(32, 32)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

# -------------------------
# 3. 메인 패널
# -------------------------
class ControlPanel(QWidget):
    def __init__(self, state: PetState, pet, app_icon: Optional[QIcon] = None, default_theme: str = "pink"):
        super().__init__()
        self.state, self.pet = state, pet
        self.theme = default_theme
        self.user_name = "나" # 사용자 이름 고정
        
        # 하위 창 인스턴스 초기화
        self.home_window = None
        self.job_window = None
        self.study_window = None
        self.name_window = None
        
        QApplication.instance().setQuitOnLastWindowClosed(False)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(400, 600)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame = StyledWidget()
        self.frame.setObjectName("WindowFrame")
        outer.addWidget(self.frame)

        frame_lay = QVBoxLayout(self.frame)
        frame_lay.setContentsMargins(0, 0, 0, 0)
        frame_lay.setSpacing(0)

        self.titlebar = TitleBar(self.frame, self)
        frame_lay.addWidget(self.titlebar)

        content_widget = QWidget()
        self.root = QVBoxLayout(content_widget)
        self.root.setContentsMargins(24, 4, 24, 4)
        self.root.setSpacing(0)
        frame_lay.addWidget(content_widget)

        self.header_widget = StyledWidget()
        self.header_widget.setObjectName("PanelHeader")
        self.header_widget.setFixedHeight(43)
        h_lay = QHBoxLayout(self.header_widget)
        h_lay.setContentsMargins(15, 0, 15, 0)
        
        self.money_btn = QPushButton(); self.money_btn.setObjectName("HeaderIconButton")
        self.money_btn.setFixedSize(28, 28)
        self.money_label = QLabel(""); self.money_label.setObjectName("MoneyLabel")
        
        self.name_label = QLabel(""); self.name_label.setObjectName("NameLabel")
        self.rename_btn = QPushButton(""); self.rename_btn.setObjectName("HeaderIconButton")
        self.rename_btn.setFixedSize(28, 28)
        self.rename_btn.clicked.connect(self.open_name_change)

        h_lay.addWidget(self.money_btn); h_lay.addWidget(self.money_label)
        h_lay.addSpacing(10); h_lay.addWidget(self.name_label); h_lay.addWidget(self.rename_btn)
        h_lay.addStretch(1)

        self.mood_label = QLabel(""); self.mood_label.setObjectName("MoodLabel")
        self.theme_btn = QPushButton(""); self.theme_btn.setObjectName("HeaderIconButton")
        self.theme_btn.setFixedSize(28, 28)
        self.theme_btn.clicked.connect(self.toggle_theme)
        
        h_lay.addWidget(self.mood_label); h_lay.addWidget(self.theme_btn)
        self.root.addWidget(self.header_widget)

        # ✅ 스크롤바 유지 및 채팅로그
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True); self.chat_log.setObjectName("ChatLog")
        self.chat_log.setFixedHeight(203)
        self.chat_log.viewport().setAutoFillBackground(False)
        self.chat_log.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        self.root.addWidget(self.chat_log)

        self.status_container = QWidget()
        status_vbox = QVBoxLayout(self.status_container)
        status_vbox.setContentsMargins(0, 8, 0, 0)
        status_vbox.setSpacing(4) 

        self.status_rows = {}
        status_info = [
            ("fun", "재미", "ic_fun.png", "GaugeFun"), 
            ("mood", "기분", "ic_mood.png", "GaugeMood"),
            ("hunger", "포만감", "ic_hunger.png", "GaugeHunger"), 
            ("energy", "에너지", "ic_energy.png", "GaugeEnergy")
        ]

        for key, kr_name, icon_name, obj_name in status_info:
            row_widget = StyledWidget()
            row_widget.setObjectName("StatusRow")
            row_widget.setFixedSize(352, 33)
            row_lay = QHBoxLayout(row_widget)
            
            row_lay.setContentsMargins(12, 0, 2, 0) 
            row_lay.setSpacing(6)

            st_btn = QPushButton(); st_btn.setObjectName("HeaderIconButton")
            st_btn.setFixedSize(28, 28)
            kr_lbl = QLabel(kr_name); kr_lbl.setObjectName("StatusNameLabel")
            track_lbl = QLabel(); track_lbl.setObjectName("BarTrack"); track_lbl.setFixedSize(246, 28)
            gauge_lbl = QLabel(track_lbl); gauge_lbl.setObjectName(obj_name); gauge_lbl.setFixedSize(0, 28)

            row_lay.addWidget(st_btn); row_lay.addWidget(kr_lbl)
            row_lay.addStretch(1); row_lay.addWidget(track_lbl)
            status_vbox.addWidget(row_widget, 0, Qt.AlignCenter)
            self.status_rows[key] = (gauge_lbl, st_btn, icon_name) 

        self.root.addWidget(self.status_container)

        self.btn_widgets = [] 
        btn_container = QWidget(); btn_container.setFixedWidth(352)
        btn_grid = QGridLayout(btn_container)
        btn_grid.setContentsMargins(4, 0, 4, 0); btn_grid.setSpacing(4)
        
        self.actions_info = [
            ("밥주기", "feed.png", self.feed_pet), ("대화", "pet.png", self.pet_pet),
            ("놀아주기", "play.png", self.play_pet), ("집", "home.png", self.open_home),
            ("알바", "job.png", self.open_job), ("공부", "study.png", self.open_study)
        ]
        
        for i, (txt, img, func) in enumerate(self.actions_info):
            btn = QPushButton(txt); btn.setObjectName("MenuButton"); btn.setFixedSize(110, 46)
            btn.clicked.connect(func)
            btn_grid.addWidget(btn, i // 3, i % 3)
            self.btn_widgets.append((btn, img))
            
        self.root.addWidget(btn_container, 0, Qt.AlignCenter)

        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.PointingHandCursor)

        self.apply_theme(self.theme)
        self._sync_ui()
        self.ui_timer = QTimer(self); self.ui_timer.timeout.connect(self._sync_ui); self.ui_timer.start(250)
        self._init_tray(app_icon)

    def apply_theme(self, theme_name: str):
        self.theme = theme_name
        qss_file = THEME_DIR / "ui.qss"
        if not qss_file.exists(): return
        with open(qss_file, "r", encoding="utf-8") as f: style = f.read()
        tp = THEME_DIR / self.theme
        mapping = {
            "window_frame": _p(tp / "window_frame.png"), "titlebar_bg": _p(tp / "window_titlebar.png"),
            "panel_header": _p(tp / "panel_header.png"), "panel_status": _p(tp / "panel_status.png"),
            "panel_chat": _p(tp / "panel_chat.png"), 
            "btn_m": _p(tp / "btn_m.png"), 
            "btn_m_press": _p(tp / "btn_m_press.png"), 
            "btn_ic": _p(tp / "btn_ic.png"), "ic_setting": _p(ICON_DIR / "ic_setting.png"), 
            "ic_min": _p(ICON_DIR / "ic_min.png"), "ic_close": _p(ICON_DIR / "ic_close.png"), 
            "btn_close_hover": _p(tp / "btn_close_hover.png"), "bar_track": _p(tp / "bar_track.png"),
            "bar_track_fun": _p(tp / "bar_track_fun.png"), "bar_track_mood": _p(tp / "bar_track_mood.png"),
            "bar_track_hunger": _p(tp / "bar_track_hunger.png"), "bar_track_energy": _p(tp / "bar_track_energy.png"),
            "text_color": "#ffffff" if self.theme == "dark" else "#333333"
        }
        for k, v in mapping.items(): style = style.replace(f"{{{k}}}", v)
        self.setStyleSheet(style)
        self._update_icons()

    def _update_icons(self):
        sys_p = ICON_DIR / "ic_main.png" 
        if sys_p.exists():
            pix = QPixmap(str(sys_p.resolve()))
            self.titlebar.sys_icon.setScaledContents(True) 
            self.titlebar.sys_icon.setPixmap(pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        coin_p = ICON_DIR / "ic_coin.png"
        if coin_p.exists():
            self.money_btn.setIcon(QIcon(str(coin_p.resolve()))); self.money_btn.setIconSize(QSize(28, 28))
        
        for btn, path in [(self.rename_btn, ICON_DIR / "ic_rename.png"), (self.theme_btn, ICON_DIR / "ic_theme.png")]:
            if path.exists(): btn.setIcon(QIcon(str(path.resolve()))); btn.setIconSize(QSize(28, 28))

        for key in self.status_rows:
            gauge, btn, img_name = self.status_rows[key]
            path = ICON_DIR / img_name
            if path.exists(): btn.setIcon(QIcon(str(path.resolve()))); btn.setIconSize(QSize(28, 28))

        for btn, img_name in self.btn_widgets:
            path = app_icon_DIR / img_name
            if path.exists(): btn.setIcon(QIcon(str(path.resolve()))); btn.setIconSize(QSize(28, 28))

    def _sync_ui(self):
        self.money_label.setText(str(int(self.state.money))); self.name_label.setText(self.state.pet_name)
        self.mood_label.setText(self.state.mood_label)
        max_w = 246
        for k, row_data in self.status_rows.items():
            gauge = row_data[0]
            val = getattr(self.state, k)
            gauge.setFixedWidth(int((val / 100) * max_w))
        self.titlebar.title_label.setText(f"{self.state.pet_name} - 메인 화면")

    def open_settings(self): pass
    def minimize_to_tray(self): self.hide()
    def quit_app(self): QApplication.instance().quit()
    def _init_tray(self, icon):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self.tray = QSystemTrayIcon(icon if icon else self.windowIcon(), self)
        m = QMenu(); m.addAction("열기", lambda: (self.show(), self.raise_())); m.addAction("종료", self.quit_app)
        self.tray.setContextMenu(m); self.tray.show()
    def toggle_theme(self): self.apply_theme("dark" if self.theme == "pink" else "pink")


    # ----------------------------------------------------
    # ✅ 펫 상호작용 코어 로직 (폰트 축소 및 하위 창 반응 보장)
    # ----------------------------------------------------
    def _active_pet_for_chat(self):
        """현재 화면에 떠 있는 창의 실제 펫 추적 (하우스 펫 변수명 오류 수정)"""
        # ✅ 집 창이 열려있으면 'house_pet'을 타겟으로 잡음
        if self.home_window and self.home_window.isVisible() and hasattr(self.home_window, 'house_pet'):
            return self.home_window.house_pet
            
        if self.job_window and self.job_window.isVisible() and hasattr(self.job_window, 'pet'):
            return self.job_window.pet
        if self.study_window and self.study_window.isVisible() and hasattr(self.study_window, 'pet'):
            return self.study_window.pet
            
        return self.pet

    def _format_stat(self, stat_name: str, change_val: int) -> str:
        """폰트 크기를 11px(또는 9pt)로 강제 축소하여 시각적 안정감 부여"""
        f_style = "font-size:11px; font-weight:bold;" 
        if change_val > 0:
            return f"<span style='color:#FF5E5E; {f_style}'>▲ {stat_name} {change_val}</span>"
        elif change_val < 0:
            return f"<span style='color:#4A90E2; {f_style}'>▼ {stat_name} {abs(change_val)}</span>"
        return ""

    def _delayed_pet_response(self, target, pet_msg, stats_html, anim_callback):
        log_html = (
            f"<b>{self.state.pet_name}</b> : {pet_msg}<br>"
            f"&nbsp;&nbsp;{stats_html}<br>"
        )
        self.chat_log.append(log_html)
        self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())
        
        # 애니메이션 실행
        if anim_callback: 
            anim_callback()
            
        # 하위 창 펫 객체의 isHidden() 오작동을 피하기 위해 target 유무만 검증
        if target:
            trigger_pet_action_bubble(target, self.chat_log, [pet_msg])

    def handle_interaction(self, user_action_msg, normal_logic):
        target = self._active_pet_for_chat()
        
        self.user_name = "고요"
        self.chat_log.append(f"<span style='color:#aaaaaa;'><b>{self.user_name}</b> : {user_action_msg}</span>")
        self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())

        is_sleeping = getattr(target, "is_sleeping", False) or self.state.energy < 4

        def response():
            if is_sleeping:
                dec_mood = -random.randint(1, 20)
                self.state.mood = clamp(self.state.mood + dec_mood)
                msg = random.choice(["음냐... 피곤해...", "아 왜 깨워...", "ZZZ... 안 놀아..."])
                stats_html = self._format_stat('기분', dec_mood)
                
                def sleep_anim():
                    if hasattr(target, "start_shake"): target.start_shake(sec=0.5, strength=3)
                    if hasattr(target, "start_sleep_for_60s"):
                        QTimer.singleShot(600, target.start_sleep_for_60s)
                
                self._delayed_pet_response(target, msg, stats_html, sleep_anim)
            else:
                normal_logic(target)

        QTimer.singleShot(500, response)

    def feed_pet(self):
        def normal_logic(target):
            inc_hunger = random.randint(1, 20)
            inc_mood = random.randint(1, 10)
            self.state.hunger = clamp(self.state.hunger + inc_hunger)
            self.state.mood = clamp(self.state.mood + inc_mood)
            
            msg = random.choice(["냠냠! 맛있어!", "배부르다 찍!", "밥 최고!"])
            stats_html = f"{self._format_stat('포만감', inc_hunger)} &nbsp;&nbsp; {self._format_stat('기분', inc_mood)}"
            
            def anim():
                # 집 창 펫 객체 모델 호환을 위해 hasattr 다중 체크
                if hasattr(target, "trigger_eat_visual"): target.trigger_eat_visual()
                elif hasattr(target, "set_action"): target.set_action("eat")
                
            self._delayed_pet_response(target, msg, stats_html, anim)
            
        self.handle_interaction("🍚 밥을 줬다!", normal_logic)

    def pet_pet(self):
        def normal_logic(target):
            inc_mood = random.randint(1, 20)
            inc_fun = random.randint(1, 20)
            self.state.mood = clamp(self.state.mood + inc_mood)
            self.state.fun = clamp(self.state.fun + inc_fun)
            
            msg = random.choice(["헤헤 기분 좋아 💗", "더 쓰다듬어줘!", "따뜻해..."])
            stats_html = f"{self._format_stat('기분', inc_mood)} &nbsp;&nbsp; {self._format_stat('재미', inc_fun)}"
            
            def anim():
                if hasattr(target, "start_shake"): target.start_shake(sec=0.4, strength=2)
                elif hasattr(target, "set_action"): target.set_action("jump")
                
            self._delayed_pet_response(target, msg, stats_html, anim)
            
        self.handle_interaction("💗 쓰다듬었다!", normal_logic)

    def play_pet(self):
        def normal_logic(target):
            dec_energy = -random.randint(1, 20)
            inc_fun = random.randint(1, 20)
            inc_mood = random.randint(1, 20)
            
            max_e = getattr(self.state, 'max_energy', 100.0)
            self.state.energy = clamp(self.state.energy + dec_energy, 0.0, max_e)
            self.state.fun = clamp(self.state.fun + inc_fun)
            self.state.mood = clamp(self.state.mood + inc_mood)
            
            msg = random.choice(["야호! 재밌다!", "우다다다!", "한 번 더 놀자!"])
            stats_html = (
                f"{self._format_stat('에너지', dec_energy)} &nbsp;&nbsp; "
                f"{self._format_stat('재미', inc_fun)} &nbsp;&nbsp; "
                f"{self._format_stat('기분', inc_mood)}"
            )
            
            def anim():
                if hasattr(target, "do_jump"): target.do_jump(strength=14)
                elif hasattr(target, "set_action"): target.set_action("play")
                
                if self.state.energy < 4 and hasattr(target, "start_sleep_for_60s"):
                    QTimer.singleShot(1000, target.start_sleep_for_60s)
                    
            self._delayed_pet_response(target, msg, stats_html, anim)
            
        self.handle_interaction("🎮 같이 놀았다!", normal_logic)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._old_pos = e.globalPosition().toPoint()
    def mouseMoveEvent(self, e):
        if hasattr(self, '_old_pos'):
            delta = e.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._old_pos = e.globalPosition().toPoint()

    # -------------------------
    # 창 관리 및 펫 복구 로직
    # -------------------------
    def _hook_close_event(self, window):
        original_close = window.closeEvent
        def closeEvent(event):
            if self.pet: self.pet.show()
            original_close(event)
        window.closeEvent = closeEvent

    def open_home(self):
        if self.pet: self.pet.hide() 
        if self.home_window is None:
            self.home_window = HouseWindow(self.state, self.windowIcon())
            self._hook_close_event(self.home_window)
        self.home_window.show(); self.home_window.raise_(); self.home_window.activateWindow()

    def open_job(self):
        if self.pet: self.pet.hide()
        if self.job_window is None:
            self.job_window = JobWindow(self.state, self.windowIcon())
            self._hook_close_event(self.job_window)
        self.job_window.show(); self.job_window.raise_(); self.job_window.activateWindow()

    def open_study(self):
        if self.pet: self.pet.hide()
        if self.study_window is None:
            self.study_window = StudyWindow(self.state, self.windowIcon())
            self._hook_close_event(self.study_window)
        self.study_window.show(); self.study_window.raise_(); self.study_window.activateWindow()

    def open_home(self):
        if self.pet: self.pet.hide() 
        if self.home_window is None:
            # ✅ 두 번째 인자로 self.pet 추가
            self.home_window = HouseWindow(self.state, self.pet, self.windowIcon())
            self._hook_close_event(self.home_window)
        self.home_window.show(); self.home_window.raise_(); self.home_window.activateWindow()

    def open_name_change(self):
        if self.name_window is None:
            self.name_window = NameWindow(self.state, self.windowIcon())
        self.name_window.show(); self.name_window.raise_()