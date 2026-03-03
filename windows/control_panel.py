import time
import json
import random
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer, QPoint
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QVBoxLayout, QWidget, QMenu, QSystemTrayIcon,
    QStyle, QStyleOption, QComboBox
)

from config import app_icon_DIR
from utils.helpers import trigger_pet_action_bubble
from state import PetState, clamp
from windows.name_window import NameWindow
from windows.house_window import HouseWindow
from windows.job_window import JobWindow
from windows.study_window import StudyWindow

# -------------------------
# 0. 다국어 관리 (i18n)
# -------------------------
class LangManager:
    def __init__(self, default_lang="ko"):
        self.lang_code = default_lang
        self.data = {}
        self.load_lang(default_lang)

    def load_lang(self, lang_code):
        self.lang_code = lang_code
        # 'asset/lang/' 경로 (스크린샷 기준)
        path = Path(__file__).resolve().parents[1] / "asset" / "lang" / f"{lang_code}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            print(f"DEBUG: Lang file not found at {path}")

    def get(self, key_path, default=""):
        keys = key_path.split(".")
        temp = self.data
        try:
            for k in keys:
                temp = temp[k]
            return temp
        except (KeyError, TypeError):
            return default

# -------------------------
# Helpers
# -------------------------
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]

THEME_BASE_DIR = _project_root() / "asset" / "theme"

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
        self.setFixedHeight(36) 
        
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0) 
        lay.setSpacing(6) 
        
        self.sys_icon = QLabel()
        self.sys_icon.setObjectName("SystemIcon")
        self.sys_icon.setFixedSize(20, 20) 
        lay.addWidget(self.sys_icon)
        
        self.title_label = QLabel()
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setStyleSheet("font-size: 12px;") 
        lay.addWidget(self.title_label)
        
        lay.addStretch(1)
        
        self.set_btn = QPushButton()
        self.min_btn = QPushButton()
        self.close_btn = QPushButton()
        
        for btn, slot in [(self.set_btn, self.panel.open_settings), 
                          (self.min_btn, self.panel.minimize_to_tray), 
                          (self.close_btn, self.panel.quit_app)]:
            btn.setFixedSize(20, 20) 
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("background: transparent; border: none;") 
            btn.clicked.connect(slot)
            lay.addWidget(btn)

# -------------------------
# 3. 메인 패널
# -------------------------
class ControlPanel(QWidget):
    def __init__(self, state: PetState, pet, app_icon: Optional[QIcon] = None, default_theme: str = "pink", default_lang: str = "ko"):
        super().__init__()
        self.state = state
        self.pet = pet
        self.theme = default_theme
        self.lang = LangManager(default_lang)
        self.user_name = "나"
        
        self.home_window = None
        self.job_window = None
        self.study_window = None
        self.name_window = None
        
        QApplication.instance().setQuitOnLastWindowClosed(False)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(300, 380)
        self.setWindowOpacity(0.95) 

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
        self.root.setContentsMargins(10, 2, 10, 2) 
        self.root.setSpacing(4) 
        frame_lay.addWidget(content_widget)

        # 헤더 영역 (돈, 이름, 감정)
        self.header_widget = StyledWidget()
        self.header_widget.setObjectName("PanelHeader")
        self.header_widget.setFixedSize(280, 36) 
        h_lay = QHBoxLayout(self.header_widget)
        h_lay.setContentsMargins(10, 0, 10, 0) 
        h_lay.setSpacing(8)
        
        self.money_icon = QLabel()
        self.money_icon.setFixedSize(20, 20)
        self.money_label = QLabel("0")
        self.money_label.setObjectName("MoneyLabel")
        self.money_label.setStyleSheet("font-size: 11px;") 

        self.name_label = QLabel("")
        self.name_label.setObjectName("NameLabel")
        self.name_label.setStyleSheet("font-weight: bold; font-size: 12px;") 

        self.mood_label = QLabel("")
        self.mood_label.setObjectName("MoodLabel")
        self.mood_label.setAlignment(Qt.AlignCenter)
        self.mood_label.setStyleSheet("background: rgba(255,255,255,0.2); border-radius: 6px; padding: 2px 6px; font-size: 11px; height: 18px;")

        h_lay.addWidget(self.money_icon)
        h_lay.addWidget(self.money_label)
        h_lay.addStretch(1)
        h_lay.addWidget(self.name_label)
        h_lay.addStretch(1)
        h_lay.addWidget(self.mood_label)
        self.root.addWidget(self.header_widget)

        # 채팅창
        chat_bg_widget = StyledWidget()
        chat_bg_widget.setObjectName("ChatLog") 
        chat_bg_widget.setFixedSize(280, 85) 
        chat_lay = QVBoxLayout(chat_bg_widget)
        chat_lay.setContentsMargins(8, 6, 2, 6) 
        chat_lay.setSpacing(0)

        self.chat_log = QTextEdit()
        self.chat_log.setObjectName("ChatText")
        self.chat_log.setReadOnly(True)
        self.chat_log.document().setDocumentMargin(2) 
        self.chat_log.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded) 
        self.chat_log.setStyleSheet("background: transparent; border: none;")
        self.chat_log.viewport().setAutoFillBackground(False)
        self.chat_log.setAttribute(Qt.WA_TranslucentBackground, True)
        self.chat_log.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        chat_lay.addWidget(self.chat_log)
        self.root.addWidget(chat_bg_widget, 0, Qt.AlignCenter)

        # 스탯창
        self.status_container = StyledWidget()
        self.status_container.setObjectName("PanelStatus") 
        self.status_container.setFixedSize(280, 120) 
        status_vbox = QVBoxLayout(self.status_container)
        status_vbox.setContentsMargins(8, 4, 8, 4) 
        status_vbox.setSpacing(0) 

        self.status_rows = {}
        status_info = [
            ("fun", "ic_fun.png", "GaugeFun"), 
            ("mood", "ic_mood.png", "GaugeMood"),
            ("hunger", "ic_hunger.png", "GaugeHunger"), 
            ("energy", "ic_energy.png", "GaugeEnergy")
        ]

        for key, icon_name, obj_name in status_info:
            row_widget = QWidget() 
            row_widget.setObjectName("StatusRow")
            row_widget.setFixedSize(264, 28) 
            row_lay = QHBoxLayout(row_widget)
            row_lay.setContentsMargins(0, 0, 0, 0) 
            row_lay.setSpacing(4) 

            st_icon = QLabel()
            st_icon.setObjectName("StatusIcon")
            st_icon.setFixedSize(20, 20); st_icon.setAlignment(Qt.AlignCenter)

            kr_lbl = QLabel()
            kr_lbl.setObjectName("StatusNameLabel")
            kr_lbl.setFixedWidth(36); kr_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter); kr_lbl.setStyleSheet("font-size: 11px; background: transparent;")
            
            track_lbl = QLabel()
            track_lbl.setObjectName("BarTrack"); track_lbl.setFixedSize(180, 18) 
            gauge_lbl = QLabel(track_lbl); gauge_lbl.setObjectName(obj_name); gauge_lbl.setFixedSize(0, 18)
            val_lbl = QLabel(track_lbl); val_lbl.setFixedSize(180, 18); val_lbl.setAlignment(Qt.AlignCenter); val_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 10px; background: transparent;")

            row_lay.addWidget(st_icon); row_lay.addWidget(kr_lbl); row_lay.addSpacing(4); row_lay.addWidget(track_lbl); row_lay.addStretch(1) 
            status_vbox.addWidget(row_widget, 0, Qt.AlignCenter)
            self.status_rows[key] = (gauge_lbl, st_icon, icon_name, val_lbl, kr_lbl)

        self.root.addWidget(self.status_container, 0, Qt.AlignCenter)

        # 하단 버튼
        self.btn_widgets = [] 
        btn_container = QWidget(); btn_container.setFixedWidth(280) 
        btn_grid = QGridLayout(btn_container); btn_grid.setContentsMargins(0, 0, 0, 0); btn_grid.setSpacing(4) 
        self.actions_setup_list = [("feed", "feed.png", self.feed_pet), ("chat", "pet.png", self.pet_pet), ("play", "play.png", self.play_pet),
                                  ("home", "home.png", self.open_home), ("job", "job.png", self.open_job), ("study", "study.png", self.open_study)]
        for i, (l_key, img, func) in enumerate(self.actions_setup_list):
            btn = QPushButton(); btn.setObjectName("MenuButton")
            btn.setFixedSize(84, 28); btn.clicked.connect(func)
            btn_grid.addWidget(btn, i // 3, i % 3); self.btn_widgets.append((btn, img, l_key))
        self.root.addWidget(btn_container, 0, Qt.AlignCenter)

        self.guide_label = QLabel(); self.guide_label.setAlignment(Qt.AlignCenter)
        self.guide_label.setStyleSheet("color: #fff; font-size: 9px; font-weight: bold;") 
        self.root.addWidget(self.guide_label, 0, Qt.AlignCenter)

        for btn in self.findChildren(QPushButton): btn.setCursor(Qt.PointingHandCursor)

        self.apply_theme(self.theme); self._init_tray(app_icon)
        self.retranslate_ui(); self._sync_ui()
        self.ui_timer = QTimer(self); self.ui_timer.timeout.connect(self._sync_ui); self.ui_timer.start(250)
        self.chat_log.append(f"<div style='color:#aaaaaa;'>{self.lang.get('ui.sys_ready')}</div>")

    # --- 다국어 및 실시간 번역 로직 ---
    def _get_localized_mood(self):
        """기분 수치에 따른 번역된 텍스트 반환"""
        m = self.state.mood
        mk = "v_happy" if m > 80 else "happy" if m > 60 else "normal" if m > 40 else "sad" if m > 20 else "angry"
        return self.lang.get(f"moods.{mk}")

    def retranslate_ui(self):
        """언어 변경 시 정적 텍스트 갱신"""
        L = self.lang
        # 윈도우 타이틀 및 가이드
        self.titlebar.title_label.setText(f"{self.state.pet_name} - {L.get('title')}")
        self.guide_label.setText(L.get("ui.guide"))
        # 하단 버튼
        for btn, _, l_key in self.btn_widgets: 
            btn.setText(L.get(f"buttons.{l_key}"))
        # 스탯 라벨
        for key, row_data in self.status_rows.items(): 
            row_data[4].setText(L.get(f"status.{key}"))
        # 시스템 트레이 메뉴
        if hasattr(self, 'action_open'):
            self.action_open.setText(L.get("ui.tray_open", "열기"))
            self.action_quit.setText(L.get("ui.tray_quit", "종료"))

    def _sync_ui(self):
        """실시간 데이터 동기화 (이름, 타이틀, 기분 반영)"""
        self.money_label.setText(str(int(self.state.money)))
        # 패널 헤더 펫 이름 반영
        self.name_label.setText(self.state.pet_name)
        # 패널 헤더 감정 상태 실시간 번역 반영
        self.mood_label.setText(self._get_localized_mood())
        # 윈도우 타이틀바 실시간 이름+언어 반영
        self.titlebar.title_label.setText(f"{self.state.pet_name} - {self.lang.get('title')}")
        
        max_w = 180 
        for k, row_data in self.status_rows.items():
            gauge, _, _, val_lbl, _ = row_data
            val = getattr(self.state, k)
            gauge.setFixedWidth(int((val / 100) * max_w))
            val_lbl.setText(f"{int(val)} / 100")

    # --- 테마 및 아이콘 (원본 로직 보존) ---
    def apply_theme(self, theme_name: str):
        self.theme = theme_name
        tp = THEME_BASE_DIR / self.theme
        ud = tp / "ui"; self.current_icon_dir = tp / "icon" 
        style = ""
        for p in [THEME_BASE_DIR / "common.qss", tp / f"{theme_name}.qss"]:
            if p.exists(): style += p.read_text(encoding="utf-8") + "\n"
        tc = "#ffffff" if self.theme == "dark" else "#703355"
        mapping = {
            "window_frame": _p(ud / "window_frame.png"), "titlebar_bg": _p(ud / "window_titlebar.png"),
            "panel_header": _p(ud / "panel_header.png"), "panel_status": _p(ud / "panel_status.png"),
            "panel_chat": _p(ud / "panel_chat.png"), "btn_m": _p(ud / "btn_m.png"), 
            "btn_m_press": _p(ud / "btn_m_press.png"), "btn_ic": _p(ud / "btn_ic.png"), 
            "btn_close_hover": _p(ud / "btn_close_hover.png"), "bar_track": _p(ud / "bar_track.png"),
            "bar_track_fun": _p(ud / "bar_track_fun.png"), "bar_track_mood": _p(ud / "bar_track_mood.png"),
            "bar_track_hunger": _p(ud / "bar_track_hunger.png"), "bar_track_energy": _p(ud / "bar_track_energy.png"),
            "text_color": tc, "ic_setting": _p(self.current_icon_dir / "ic_setting.png"),
            "ic_min": _p(self.current_icon_dir / "ic_min.png"), "ic_close": _p(self.current_icon_dir / "ic_close.png")
        }
        for k, v in mapping.items(): style = style.replace(f"{{{k}}}", v)
        if Path(_p(ud / "panel_chat.png")).exists():
            style += f"\n#ChatLog {{ border-image: url('{_p(ud/'panel_chat.png')}') 0 0 0 0 stretch stretch; }}"
        if Path(_p(ud / "panel_status.png")).exists():
            style += f"\n#PanelStatus {{ border-image: url('{_p(ud/'panel_status.png')}') 0 0 0 0 stretch stretch; }}"
        self.setStyleSheet(style); self._update_icons()

    def _update_icons(self):
        sys_p = self.current_icon_dir / "ic_main.png" 
        if sys_p.exists():
            self.titlebar.sys_icon.setPixmap(QPixmap(str(sys_p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)) 
        for btn, img in [(self.titlebar.set_btn, "ic_setting.png"), (self.titlebar.min_btn, "ic_min.png"), (self.titlebar.close_btn, "ic_close.png")]:
            p = self.current_icon_dir / img
            if p.exists(): btn.setIcon(QIcon(str(p.resolve()))); btn.setIconSize(QSize(20, 20))
        for k, r in self.status_rows.items():
            p = self.current_icon_dir / r[2]
            if p.exists(): r[1].setPixmap(QPixmap(str(p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        for b, img, _ in self.btn_widgets:
            p = self.current_icon_dir / img
            if not p.exists(): p = app_icon_DIR / img
            if p.exists(): b.setIcon(QIcon(str(p.resolve()))); b.setIconSize(QSize(20, 20))

    # --- 윈도우 관리 (문법 에러 수정 완료) ---
    def _close_all_sub_windows(self, except_win=None):
        for w in [self.home_window, self.job_window, self.study_window]:
            if w and w != except_win and w.isVisible(): 
                w.close()

    def _sync_and_show_main_pet(self, sub_window):
        if not any(w and w != sub_window and w.isVisible() for w in [self.home_window, self.job_window, self.study_window]):
            sub_pet = getattr(sub_window, 'house_pet', getattr(sub_window, 'pet', None))
            if sub_pet and self.pet:
                self.pet.sleeping = getattr(sub_pet, 'sleeping', False)
                self.pet.sleep_end_at = getattr(sub_pet, 'sleep_end_at', 0)
                m = "sleep" if self.pet.sleeping else "normal"
                self.pet.set_mode(m, sec=max(0.1, self.pet.sleep_end_at - time.time()) if self.pet.sleeping else 99999)
            if self.pet: self.pet.show(); self.pet.raise_()

    def open_home(self):
        self._close_all_sub_windows()
        is_s, s_e = (self.pet.sleeping, self.pet.sleep_end_at) if self.pet else (False, 0)
        if self.pet: 
            self.pet.hide() 
        if self.home_window is None:
            self.home_window = HouseWindow(self.state, self.pet, self.windowIcon())
            orig_c = self.home_window.closeEvent
            self.home_window.closeEvent = lambda e: (self._sync_and_show_main_pet(self.home_window), orig_c(e))
        if is_s and hasattr(self.home_window, 'house_pet'):
            h_p = self.home_window.house_pet; h_p.sleeping = True; h_p.sleep_end_at = s_e
            h_p.set_mode("sleep", sec=max(0.1, s_e - time.time()))
        self.home_window.show(); self.home_window.raise_()

    def open_job(self):
        self._close_all_sub_windows()
        if self.pet: 
            self.pet.hide()
        if self.job_window is None:
            self.job_window = JobWindow(self.state, self.windowIcon())
            orig_c = self.job_window.closeEvent
            self.job_window.closeEvent = lambda e: (self._sync_and_show_main_pet(self.job_window), orig_c(e))
        self.job_window.show(); self.job_window.raise_()

    def open_study(self):
        self._close_all_sub_windows()
        if self.pet: 
            self.pet.hide()
        if self.study_window is None:
            self.study_window = StudyWindow(self.state, self.windowIcon())
            orig_c = self.study_window.closeEvent
            self.study_window.closeEvent = lambda e: (self._sync_and_show_main_pet(self.study_window), orig_c(e))
        self.study_window.show(); self.study_window.raise_()

    def open_settings(self):
        if not hasattr(self, 'settings_win') or self.settings_win is None:
            self.settings_win = SettingsWindow(self.state, self)
        pos = self.geometry().topRight(); self.settings_win.move(pos.x() + 10, pos.y())
        self.settings_win.show(); self.settings_win.raise_()

    def _init_tray(self, icon):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self.tray = QSystemTrayIcon(icon if icon else self.windowIcon(), self)
        self.tray_menu = QMenu()
        self.action_open = self.tray_menu.addAction("", lambda: (self.show(), self.raise_()))
        self.action_quit = self.tray_menu.addAction("", lambda: QApplication.instance().quit())
        self.tray.setContextMenu(self.tray_menu); self.tray.show()

    def minimize_to_tray(self): self.hide()
    def quit_app(self): QApplication.instance().quit()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._old_pos = e.globalPosition().toPoint()
    def mouseMoveEvent(self, e):
        if hasattr(self, '_old_pos'):
            delta = e.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y()); self._old_pos = e.globalPosition().toPoint()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape: self.minimize_to_tray()
        else: super().keyPressEvent(event)

    # --- 상호작용 및 채팅 ---
    def _active_pet_for_chat(self):
        for w in [self.home_window, self.job_window, self.study_window]:
            if w and w.isVisible(): return getattr(w, 'house_pet', getattr(w, 'pet', self.pet))
        return self.pet

    def _format_stat(self, k, v):
        n = self.lang.get(f"status.{k}"); s = "font-size:11px; font-weight:bold;" 
        return f"<span style='color:{('#FF5E5E' if v>0 else '#4A90E2')}; {s}'>{'▲' if v>0 else '▼'}{n} {abs(v)}</span>"

    def _delayed_pet_response(self, target, msg, stats, anim):
        sb = f"<br>&nbsp;└ <span style='background:rgba(255,160,209,0.15);'>{stats}</span>" if stats else ""
        self.chat_log.append(f"<div><b>{self.state.pet_name}</b> : {msg}{sb}</div>")
        self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())
        if anim: anim()
        if target: trigger_pet_action_bubble(target, self.chat_log, [msg])

    def handle_interaction(self, uk, logic):
        t = self._active_pet_for_chat(); self.chat_log.append(f"<div style='color:#888;'><b>{self.user_name}</b> : {self.lang.get('interactions.'+uk)}</div>")
        is_s = getattr(t, "sleeping", False) or (hasattr(t, "sleep_end_at") and time.time() < t.sleep_at)
        def resp():
            if is_s:
                dv = -random.randint(5, 15); self.state.mood = clamp(self.state.mood + dv)
                self._delayed_pet_response(t, random.choice(self.lang.get("interactions.sleep_pet")), self._format_stat('mood', dv), lambda: t.start_shake(0.5, 3) if hasattr(t, 'start_shake') else None)
            else: logic(t)
        QTimer.singleShot(100, resp)

    def feed_pet(self):
        def f(t):
            h, m = random.randint(1, 20), random.randint(1, 10); self.state.hunger, self.state.mood = clamp(self.state.hunger+h), clamp(self.state.mood+m)
            self._delayed_pet_response(t, random.choice(self.lang.get("interactions.feed_pet")), f"{self._format_stat('hunger',h)} {self._format_stat('mood',m)}", lambda: t.trigger_eat_visual() if hasattr(t, 'trigger_eat_visual') else t.set_action("eat"))
        self.handle_interaction("feed_user", f)

    def pet_pet(self):
        def f(t):
            m, f = random.randint(1, 20), random.randint(1, 20); self.state.mood, self.state.fun = clamp(self.state.mood+m), clamp(self.state.fun+f)
            self._delayed_pet_response(t, random.choice(self.lang.get("interactions.chat_pet")), f"{self._format_stat('mood',m)} {self._format_stat('fun',f)}", lambda: t.start_shake(0.4, 2) if hasattr(t, 'start_shake') else t.set_action("jump"))
        self.handle_interaction("chat_user", f)

    def play_pet(self):
        def f(t):
            e, f, m = -random.randint(1, 20), random.randint(1, 20), random.randint(1, 20); self.state.energy = clamp(self.state.energy+e, 0, 100); self.state.fun, self.state.mood = clamp(self.state.fun+f), clamp(self.state.mood+m)
            def a():
                if hasattr(t, 'do_jump'): t.do_jump(14)
                if self.state.energy < 4 and hasattr(t, 'start_sleep_for_60s'): QTimer.singleShot(1000, t.start_sleep_for_60s)
            self._delayed_pet_response(t, random.choice(self.lang.get("interactions.play_pet")), f"{self._format_stat('energy',e)} {self._format_stat('fun',f)} {self._format_stat('mood',m)}", a)
        self.handle_interaction("play_user", f)

# -------------------------
# 4. 설정 창
# -------------------------
class SettingsWindow(StyledWidget):
    def __init__(self, state, panel):
        super().__init__(); self.state, self.panel = state, panel
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool); self.setFixedSize(300, 420); self.setObjectName("SettingsWindow")
        lay = QVBoxLayout(self); lay.setContentsMargins(20, 20, 20, 20); lay.setSpacing(10)
        self.tl = QLabel(); self.tl.setStyleSheet("font-size: 16px; font-weight: bold; color: white;"); lay.addWidget(self.tl)
        self.ul = QLabel(); lay.addWidget(self.ul); self.ui = QTextEdit(); self.ui.setFixedHeight(30); self.ui.setText(panel.user_name); lay.addWidget(self.ui)
        self.pl = QLabel(); lay.addWidget(self.pl); self.pi = QTextEdit(); self.pi.setFixedHeight(30); self.pi.setText(state.pet_name); lay.addWidget(self.pi)
        self.thl = QLabel(); lay.addWidget(self.thl)
        t_lay = QHBoxLayout()
        for t in ["pink", "dark"]:
            b = QPushButton(t.capitalize()); b.clicked.connect(lambda _, n=t: self.panel.apply_theme(n)); t_lay.addWidget(b)
        lay.addLayout(t_lay)
        self.ll = QLabel(); lay.addWidget(self.ll); self.lc = QComboBox(); self.lc.addItems(["ko", "en"]); self.lc.setCurrentText(panel.lang.lang_code); lay.addWidget(self.lc)
        lay.addStretch(); self.sb = QPushButton(); self.sb.setFixedHeight(36); self.sb.clicked.connect(self.save); lay.addWidget(self.sb)
        self.retranslate_ui()

    def retranslate_ui(self):
        L = self.panel.lang
        self.tl.setText(L.get("ui.settings")); self.ul.setText(L.get("ui.user_name")); self.pl.setText(L.get("ui.pet_name"))
        self.thl.setText(L.get("ui.theme")); self.ll.setText(L.get("ui.lang")); self.sb.setText(L.get("ui.save"))

    def save(self):
        u, p, l = self.ui.toPlainText().strip(), self.pi.toPlainText().strip(), self.lc.currentText()
        if u: self.panel.user_name = u
        if p: self.state.pet_name = p
        if l != self.panel.lang.lang_code: self.panel.lang.load_lang(l); self.panel.retranslate_ui()
        self.panel._sync_ui(); self.close()