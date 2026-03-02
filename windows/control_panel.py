import random
import time
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
        self.setFixedHeight(44) # 48 -> 44 축소
        
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8) 
        
        self.sys_icon = QLabel()
        self.sys_icon.setObjectName("SystemIcon")
        self.sys_icon.setFixedSize(20, 20) # 24 -> 20 축소
        lay.addWidget(self.sys_icon)
        
        self.title_label = QLabel("라이미 - Panel")
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setStyleSheet("font-size: 13px;")
        lay.addWidget(self.title_label)
        
        lay.addStretch(1)
        
        self.set_btn = QPushButton(); self.set_btn.setObjectName("SettingButton")
        self.min_btn = QPushButton(); self.min_btn.setObjectName("MinButton")
        self.close_btn = QPushButton(); self.close_btn.setObjectName("CloseButton")
        
        for btn, slot in [(self.set_btn, self.panel.open_settings), 
                          (self.min_btn, self.panel.minimize_to_tray), 
                          (self.close_btn, self.panel.quit_app)]:
            btn.setFixedSize(28, 28) # 32 -> 28 축소
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
        self.user_name = "고요"
        
        self.home_window = None
        self.job_window = None
        self.study_window = None
        self.name_window = None
        
        QApplication.instance().setQuitOnLastWindowClosed(False)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(360, 520) # ✅ 360x520 크기 축소

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
        self.root.setContentsMargins(20, 4, 20, 4)
        self.root.setSpacing(0)
        frame_lay.addWidget(content_widget)

        self.header_widget = StyledWidget()
        self.header_widget.setObjectName("PanelHeader")
        self.header_widget.setFixedHeight(46) # 50 -> 46 축소
        h_lay = QHBoxLayout(self.header_widget)
        h_lay.setContentsMargins(12, 0, 12, 0)
        h_lay.setSpacing(10)
        
        self.money_icon = QLabel(); self.money_icon.setFixedSize(22, 22)
        self.money_label = QLabel("0"); self.money_label.setObjectName("MoneyLabel")
        self.money_label.setStyleSheet("font-size: 11px;")
        
        self.name_label = QLabel(""); self.name_label.setObjectName("NameLabel")
        self.name_label.setStyleSheet("font-weight: bold; font-size: 12px;")

        self.mood_label = QLabel(""); self.mood_label.setObjectName("MoodLabel")
        self.mood_label.setAlignment(Qt.AlignCenter)
        self.mood_label.setStyleSheet("background: rgba(255,255,255,0.2); border-radius: 8px; padding: 2px 6px; font-size: 11px;")

        h_lay.addWidget(self.money_icon); h_lay.addWidget(self.money_label)
        h_lay.addStretch(1) 
        h_lay.addWidget(self.name_label)
        h_lay.addStretch(1)
        h_lay.addWidget(self.mood_label)
        
        self.root.addWidget(self.header_widget)
        self.root.addSpacing(6)

        # ✅ 채팅 로그 주석 처리 (UI에서 숨김)
        # self.chat_log = QTextEdit()
        # self.chat_log.setReadOnly(True); self.chat_log.setObjectName("ChatLog")
        # self.chat_log.setFixedHeight(160)
        # self.chat_log.viewport().setAutoFillBackground(False)
        # self.chat_log.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        # self.root.addWidget(self.chat_log)

        self.status_container = QWidget()
        status_vbox = QVBoxLayout(self.status_container)
        status_vbox.setContentsMargins(0, 6, 0, 0)
        status_vbox.setSpacing(3) 

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
            row_widget.setFixedSize(320, 30) # 352 -> 320 축소
            row_lay = QHBoxLayout(row_widget)
            
            row_lay.setContentsMargins(10, 0, 2, 0) 
            row_lay.setSpacing(5)

            st_btn = QPushButton(); st_btn.setObjectName("HeaderIconButton")
            st_btn.setFixedSize(24, 24)
            kr_lbl = QLabel(kr_name); kr_lbl.setObjectName("StatusNameLabel")
            kr_lbl.setStyleSheet("font-size: 11px;")
            
            track_lbl = QLabel(); track_lbl.setObjectName("BarTrack"); track_lbl.setFixedSize(215, 24) # 246 -> 215 축소
            gauge_lbl = QLabel(track_lbl); gauge_lbl.setObjectName(obj_name); gauge_lbl.setFixedSize(0, 24)
            
            val_lbl = QLabel(track_lbl)
            val_lbl.setFixedSize(215, 24)
            val_lbl.setAlignment(Qt.AlignCenter)
            val_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 10px; background: transparent;")

            row_lay.addWidget(st_btn); row_lay.addWidget(kr_lbl)
            row_lay.addStretch(1); row_lay.addWidget(track_lbl)
            status_vbox.addWidget(row_widget, 0, Qt.AlignCenter)
            
            self.status_rows[key] = (gauge_lbl, st_btn, icon_name, val_lbl)

        self.root.addWidget(self.status_container)
        self.root.addSpacing(10)

        self.btn_widgets = [] 
        btn_container = QWidget(); btn_container.setFixedWidth(320)
        btn_grid = QGridLayout(btn_container)
        btn_grid.setContentsMargins(2, 0, 2, 0); btn_grid.setSpacing(4)
        
        self.actions_info = [
            ("밥주기", "feed.png", self.feed_pet), ("대화", "pet.png", self.pet_pet),
            ("놀기", "play.png", self.play_pet), ("집", "home.png", self.open_home),
            ("알바", "job.png", self.open_job), ("공부", "study.png", self.open_study)
        ]
        
        for i, (txt, img, func) in enumerate(self.actions_info):
            btn = QPushButton(txt); btn.setObjectName("MenuButton")
            btn.setFixedSize(102, 42) # 버튼 크기 비율 맞춤
            btn.clicked.connect(func)
            btn_grid.addWidget(btn, i // 3, i % 3)
            self.btn_widgets.append((btn, img))
            
        self.root.addWidget(btn_container, 0, Qt.AlignCenter)

        self.root.addStretch(1)

        self.guide_label = QLabel("ESC = 패널 닫기")
        self.guide_label.setAlignment(Qt.AlignCenter)
        self.guide_label.setStyleSheet("color: #fff; font-size: 12px; font-weight: bold; margin-bottom: 2px;")
        self.root.addWidget(self.guide_label)

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
            self.titlebar.sys_icon.setPixmap(pix.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        coin_p = ICON_DIR / "ic_coin.png"
        if coin_p.exists():
            pix = QPixmap(str(coin_p.resolve())).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.money_icon.setPixmap(pix)
        
        for key in self.status_rows:
            gauge, btn, img_name, val_lbl = self.status_rows[key]
            path = ICON_DIR / img_name
            if path.exists(): 
                btn.setIcon(QIcon(str(path.resolve())))
                btn.setIconSize(QSize(24, 24))

        for btn, img_name in self.btn_widgets:
            path = app_icon_DIR / img_name
            if path.exists(): 
                btn.setIcon(QIcon(str(path.resolve())))
                btn.setIconSize(QSize(26, 26))

    def _sync_ui(self):
        self.money_label.setText(str(int(self.state.money)))
        self.name_label.setText(self.state.pet_name)
        self.mood_label.setText(self.state.mood_label)
        max_w = 215 # ✅ 동기화된 너비 수치
        
        for k, row_data in self.status_rows.items():
            gauge, _, _, val_lbl = row_data
            val = getattr(self.state, k)
            gauge.setFixedWidth(int((val / 100) * max_w))
            val_lbl.setText(f"{int(val)} / 100")
            
        self.titlebar.title_label.setText(f"{self.state.pet_name} - Panel")

    def open_settings(self):
        if not hasattr(self, 'settings_win') or self.settings_win is None:
            self.settings_win = SettingsWindow(self.state, self, self.windowIcon())
        
        pos = self.geometry().topRight()
        self.settings_win.move(pos.x() + 10, pos.y())
        self.settings_win.show()
        self.settings_win.raise_()

    def minimize_to_tray(self): self.hide()
    def quit_app(self): QApplication.instance().quit()
    def _init_tray(self, icon):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self.tray = QSystemTrayIcon(icon if icon else self.windowIcon(), self)
        m = QMenu(); m.addAction("열기", lambda: (self.show(), self.raise_())); m.addAction("종료", self.quit_app)
        self.tray.setContextMenu(m); self.tray.show()
    def toggle_theme(self): self.apply_theme("dark" if self.theme == "pink" else "pink")

    # ----------------------------------------------------
    # ✅ 펫 상호작용 코어 로직
    # ----------------------------------------------------
    def _active_pet_for_chat(self):
        if self.home_window and self.home_window.isVisible() and hasattr(self.home_window, 'house_pet'):
            return self.home_window.house_pet
        if self.job_window and self.job_window.isVisible() and hasattr(self.job_window, 'pet'):
            return self.job_window.pet
        if self.study_window and self.study_window.isVisible() and hasattr(self.study_window, 'pet'):
            return self.study_window.pet
        return self.pet

    def _format_stat(self, stat_name: str, change_val: int) -> str:
        f_style = "font-size:14px; font-weight:bold;" 
        if change_val > 0:
            return f"<span style='color:#FF5E5E; {f_style}'>▲ {stat_name} {change_val}</span>"
        elif change_val < 0:
            return f"<span style='color:#4A90E2; {f_style}'>▼ {stat_name} {abs(change_val)}</span>"
        return ""

    def _delayed_pet_response(self, target, pet_msg, stats_html, anim_callback):
        stat_box = (
            f"<table width='100%' cellpadding='0' cellspacing='4'><tr><td align='center'>"
            f"<span style='background-color: rgba(255, 160, 209, 0.15);padding: 10px 20px;'>"
            f"{stats_html}</span>"
            f"</td></tr></table>"
        )
        log_html = f"<b>{self.state.pet_name}</b> : {pet_msg}{stat_box}"
        
        # ✅ 채팅 로그 주석 처리 (에러 방지용)
        # if hasattr(self, 'chat_log'):
        #     self.chat_log.append(log_html)
        #     self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())
        
        if anim_callback: 
            anim_callback()
            
        if target:
            # chat_log 객체 대신 None 전달하여 말풍선만 출력되게 처리
            trigger_pet_action_bubble(target, getattr(self, 'chat_log', None), [pet_msg])

    def handle_interaction(self, user_action_msg, normal_logic):
        target = self._active_pet_for_chat()
        
        # ✅ 채팅 로그 주석 처리
        # if hasattr(self, 'chat_log'):
        #     self.chat_log.append(f"<span style='color:#aaaaaa;'><b>{self.user_name}</b> : {user_action_msg}</span>")
        #     self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())

        is_sleeping = getattr(target, "sleeping", False) or (hasattr(target, "sleep_end_at") and time.time() < target.sleep_end_at)

        def response():
            if is_sleeping:
                dec_mood = -random.randint(5, 15)
                self.state.mood = clamp(self.state.mood + dec_mood)
                msg = random.choice(["음냐... 더 잘래...", "아 왜 깨워...", "ZZZ... (깊은 잠)"])
                stats_html = self._format_stat('기분', dec_mood)
                
                def sleep_anim():
                    if hasattr(target, "start_shake"): target.start_shake(sec=0.5, strength=3)
                    if hasattr(target, "set_mode"):
                        remain = getattr(target, "sleep_end_at", time.time() + 5) - time.time()
                        target.set_mode("sleep", sec=max(2.0, remain))
                
                self._delayed_pet_response(target, msg, stats_html, sleep_anim)
            else:
                normal_logic(target)

        QTimer.singleShot(100, response)

    def feed_pet(self):
        def normal_logic(target):
            inc_hunger = random.randint(1, 20)
            inc_mood = random.randint(1, 10)
            self.state.hunger = clamp(self.state.hunger + inc_hunger)
            self.state.mood = clamp(self.state.mood + inc_mood)
            
            msg = random.choice(["냠냠! 맛있어!", "배부르다 찍!", "밥 최고!"])
            stats_html = f"{self._format_stat('포만감', inc_hunger)} &nbsp;&nbsp; {self._format_stat('기분', inc_mood)}"
            
            def anim():
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
            
            msg = random.choice(["헤헤 기분 좋아 💗", "쫑알쫑알!", "따뜻해..."])
            stats_html = f"{self._format_stat('기분', inc_mood)} &nbsp;&nbsp; {self._format_stat('재미', inc_fun)}"
            
            def anim():
                if hasattr(target, "start_shake"): target.start_shake(sec=0.4, strength=2)
                elif hasattr(target, "set_action"): target.set_action("jump")
                
            self._delayed_pet_response(target, msg, stats_html, anim)
            
        self.handle_interaction("💗 대화를 나누었다!", normal_logic)

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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.minimize_to_tray()
        else:
            super().keyPressEvent(event)

    # -------------------------
    # 창 관리 및 펫 상태 동기화
    # -------------------------
    def _close_all_sub_windows(self, except_win=None):
        """✅ 창 중복 실행 방지 헬퍼"""
        for w in [self.home_window, self.job_window, self.study_window]:
            if w and w != except_win and w.isVisible():
                w.close()

    def _sync_and_show_main_pet(self, sub_window):
        """하위 창이 닫힐 때 펫 상태 메인 복사 및 표시"""
        # 다른 하위 창이 하나라도 열려 있으면 메인 펫 부활 생략 (중복 방지)
        other_open = False
        for w in [self.home_window, self.job_window, self.study_window]:
            if w and w != sub_window and w.isVisible():
                other_open = True
                break

        if not other_open:
            sub_pet = getattr(sub_window, 'house_pet', getattr(sub_window, 'pet', None))
            if sub_pet and self.pet:
                if getattr(sub_pet, 'sleeping', False):
                    self.pet.sleeping = True
                    self.pet.sleep_end_at = sub_pet.sleep_end_at
                    remain = max(0.1, sub_pet.sleep_end_at - time.time())
                    self.pet.set_mode("sleep", sec=remain)
                else:
                    self.pet.sleeping = False
                    self.pet.set_mode("normal", sec=99999)
            
            if self.pet:
                self.pet.show()
                self.pet.raise_()

    def open_home(self):
        self._close_all_sub_windows() # 겹침 방지
        is_sleeping = False
        sleep_end = 0
        if self.pet:
            is_sleeping = self.pet.sleeping
            sleep_end = self.pet.sleep_end_at
            self.pet.hide() 

        if self.home_window is None:
            self.home_window = HouseWindow(self.state, self.pet, self.windowIcon())
            orig_close = self.home_window.closeEvent
            def close_wrapper(e):
                self._sync_and_show_main_pet(self.home_window)
                orig_close(e)
            self.home_window.closeEvent = close_wrapper
        
        if is_sleeping and hasattr(self.home_window, 'house_pet'):
            h_pet = self.home_window.house_pet
            h_pet.sleeping = True
            h_pet.sleep_end_at = sleep_end
            remain = max(0.1, sleep_end - time.time())
            h_pet.set_mode("sleep", sec=remain)

        self.home_window.show()
        self.home_window.raise_()
        self.home_window.activateWindow()

    def open_job(self):
        self._close_all_sub_windows() # 겹침 방지
        if self.pet: self.pet.hide()
        if self.job_window is None:
            self.job_window = JobWindow(self.state, self.windowIcon())
            orig_close = self.job_window.closeEvent
            def close_wrapper(e):
                self._sync_and_show_main_pet(self.job_window)
                orig_close(e)
            self.job_window.closeEvent = close_wrapper
        self.job_window.show(); self.job_window.raise_(); self.job_window.activateWindow()

    def open_study(self):
        self._close_all_sub_windows() # 겹침 방지
        if self.pet: self.pet.hide()
        if self.study_window is None:
            self.study_window = StudyWindow(self.state, self.windowIcon())
            orig_close = self.study_window.closeEvent
            def close_wrapper(e):
                self._sync_and_show_main_pet(self.study_window)
                orig_close(e)
            self.study_window.closeEvent = close_wrapper
        self.study_window.show(); self.study_window.raise_(); self.study_window.activateWindow()

    def open_name_change(self):
        if self.name_window is None:
            self.name_window = NameWindow(self.state, self.windowIcon())
        self.name_window.show(); self.name_window.raise_()

# -------------------------
# 4. 설정창
# -------------------------
class SettingsWindow(StyledWidget):
    def __init__(self, state: PetState, panel: "ControlPanel", icon: QIcon):
        super().__init__()
        self.state, self.panel = state, panel
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFixedSize(300, 420)
        self.setObjectName("SettingsWindow")
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)
        
        title = QLabel("⚙️ 설정"); title.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        lay.addWidget(title)

        lay.addWidget(QLabel("👤 내 이름 (사용자)"))
        self.user_input = QTextEdit(); self.user_input.setFixedHeight(35)
        self.user_input.setText(self.panel.user_name)
        lay.addWidget(self.user_input)

        lay.addWidget(QLabel("🐾 펫 이름"))
        self.pet_input = QTextEdit(); self.pet_input.setFixedHeight(35)
        self.pet_input.setText(self.state.pet_name)
        lay.addWidget(self.pet_input)
        
        lay.addWidget(QLabel("🎨 테마 선택"))
        theme_lay = QHBoxLayout()
        for t in ["pink", "dark"]:
            btn = QPushButton(t.capitalize())
            btn.clicked.connect(lambda _, name=t: self.panel.apply_theme(name))
            theme_lay.addWidget(btn)
        lay.addLayout(theme_lay)

        lay.addStretch()
        
        save_btn = QPushButton("설정 저장 및 닫기")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self.save_settings)
        lay.addWidget(save_btn)

    def save_settings(self):
        new_user = self.user_input.toPlainText().strip()
        new_pet = self.pet_input.toPlainText().strip()
        
        if new_user: self.panel.user_name = new_user
        if new_pet: self.state.pet_name = new_pet
        
        self.panel._sync_ui() 
        self.close()