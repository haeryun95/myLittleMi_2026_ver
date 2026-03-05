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
        lay.setContentsMargins(10, 0, 10, 0); lay.setSpacing(6)

        self.sys_icon = QLabel()
        self.sys_icon.setObjectName("SystemIcon")
        self.sys_icon.setFixedSize(20, 20)
        lay.addWidget(self.sys_icon)

        self.title_label = QLabel()
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setStyleSheet("font-size: 11px;")
        lay.addWidget(self.title_label)

        lay.addStretch(1)
        self.set_btn = QPushButton(); self.min_btn = QPushButton(); self.close_btn = QPushButton()

        for btn, slot in [(self.set_btn, self.panel.open_settings),
                          (self.min_btn, self.panel.minimize_to_tray),
                          (self.close_btn, self.panel.quit_app)]:
            btn.setFixedSize(20, 20); btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("background: transparent; border: none;")
            btn.clicked.connect(slot); lay.addWidget(btn)

# -------------------------
# 2-1. Settings 전용 타이틀바 (에셋 적용용)
# -------------------------
class SettingsTitleBar(StyledWidget):
    def __init__(self, frame_parent: QWidget, win: "SettingsWindow"):
        super().__init__(frame_parent)
        self.win = win
        self.setObjectName("TitleBar")
        self.setFixedHeight(36)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0); lay.setSpacing(6)

        self.sys_icon = QLabel()
        self.sys_icon.setObjectName("SystemIcon")
        self.sys_icon.setFixedSize(20, 20)
        lay.addWidget(self.sys_icon)

        self.title_label = QLabel()
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setStyleSheet("font-size: 11px;")
        lay.addWidget(self.title_label)

        lay.addStretch(1)

        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("background: transparent; border: none;")
        self.close_btn.clicked.connect(self.win.close)
        lay.addWidget(self.close_btn)

# -------------------------
# 3. 메인 패널 (ControlPanel)
# -------------------------
class ControlPanel(QWidget):
    def __init__(self, state: PetState, pet, app_icon: Optional[QIcon] = None, default_theme: str = "pink", default_lang: str = "ko"):
        super().__init__()
        self.state, self.pet = state, pet
        self.theme = default_theme
        self.lang = LangManager(default_lang)

        # 유저 및 펫 디폴트 이름 설정
        self.user_name = self.lang.get("user_name", "나")
        if not self.state.pet_name:
            self.state.pet_name = self.lang.get("pet_name", "라이미")

        self.home_window = self.job_window = self.study_window = self.name_window = None
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(300, 380); self.setWindowOpacity(0.95)

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        self.frame = StyledWidget(); self.frame.setObjectName("WindowFrame")
        outer.addWidget(self.frame)

        frame_lay = QVBoxLayout(self.frame); frame_lay.setContentsMargins(0, 0, 0, 0); frame_lay.setSpacing(0)
        self.titlebar = TitleBar(self.frame, self); frame_lay.addWidget(self.titlebar)

        content_widget = QWidget()
        self.root = QVBoxLayout(content_widget); self.root.setContentsMargins(10, 2, 10, 2); self.root.setSpacing(4)
        frame_lay.addWidget(content_widget)

        # 헤더
        self.header_widget = StyledWidget(); self.header_widget.setObjectName("PanelHeader"); self.header_widget.setFixedSize(280, 36)
        h_lay = QHBoxLayout(self.header_widget); h_lay.setContentsMargins(10, 0, 10, 0); h_lay.setSpacing(8)
        self.money_icon = QLabel(); self.money_icon.setFixedSize(20, 20)
        self.money_label = QLabel("0"); self.money_label.setObjectName("MoneyLabel")
        self.money_label.setStyleSheet("font-size: 10px;")
        self.name_label = QLabel(""); self.name_label.setObjectName("NameLabel")
        self.name_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.mood_label = QLabel(""); self.mood_label.setObjectName("MoodLabel")
        self.mood_label.setAlignment(Qt.AlignCenter)
        self.mood_label.setStyleSheet("background: rgba(255,255,255,0.2); border-radius: 6px; padding: 2px 6px; font-size: 10px;")

        h_lay.addWidget(self.money_icon); h_lay.addWidget(self.money_label); h_lay.addStretch(1)
        h_lay.addWidget(self.name_label); h_lay.addStretch(1); h_lay.addWidget(self.mood_label)
        self.root.addWidget(self.header_widget)

        # 채팅창
        chat_bg = StyledWidget(); chat_bg.setObjectName("ChatLog"); chat_bg.setFixedSize(280, 85)
        chat_lay = QVBoxLayout(chat_bg); chat_lay.setContentsMargins(8, 6, 2, 6); chat_lay.setSpacing(0)
        self.chat_log = QTextEdit(); self.chat_log.setObjectName("ChatText"); self.chat_log.setReadOnly(True)
        self.chat_log.setStyleSheet("background: transparent; border: none; font-size: 11px;")
        chat_lay.addWidget(self.chat_log); self.root.addWidget(chat_bg, 0, Qt.AlignCenter)

        # 스탯창
        self.status_container = StyledWidget(); self.status_container.setObjectName("PanelStatus"); self.status_container.setFixedSize(280, 120)
        s_vbox = QVBoxLayout(self.status_container); s_vbox.setContentsMargins(8, 4, 8, 4); s_vbox.setSpacing(0)

        self.status_rows = {}
        s_info = [("fun", "ic_fun.png", "GaugeFun"), ("mood", "ic_mood.png", "GaugeMood"),
                  ("hunger", "ic_hunger.png", "GaugeHunger"), ("energy", "ic_energy.png", "GaugeEnergy")]

        for key, icon_n, obj_n in s_info:
            row = QWidget(); row.setFixedSize(264, 28); rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(4)
            si = QLabel(); si.setFixedSize(20, 20); si.setAlignment(Qt.AlignCenter)
            kl = QLabel(); kl.setFixedWidth(36); kl.setStyleSheet("font-size: 10px; background: transparent;")
            tr = QLabel(); tr.setObjectName("BarTrack"); tr.setFixedSize(180, 18)
            ga = QLabel(tr); ga.setObjectName(obj_n); ga.setFixedSize(0, 18)
            vl = QLabel(tr); vl.setFixedSize(180, 18); vl.setAlignment(Qt.AlignCenter); vl.setStyleSheet("color: white; font-weight: bold; font-size: 9px;")
            rl.addWidget(si); rl.addWidget(kl); rl.addSpacing(4); rl.addWidget(tr); rl.addStretch(1)
            s_vbox.addWidget(row, 0, Qt.AlignCenter)
            self.status_rows[key] = (ga, si, icon_n, vl, kl)

        self.root.addWidget(self.status_container, 0, Qt.AlignCenter)

        # 하단 버튼
        self.btn_widgets = []
        bc = QWidget(); bc.setFixedWidth(280); bg = QGridLayout(bc); bg.setContentsMargins(0, 0, 0, 0); bg.setSpacing(4)
        acts = [("feed", "feed.png", self.feed_pet), ("chat", "pet.png", self.pet_pet), ("play", "play.png", self.play_pet),
                ("home", "home.png", self.open_home), ("job", "job.png", self.open_job), ("study", "study.png", self.open_study)]
        for i, (k, img, f) in enumerate(acts):
            b = QPushButton(); b.setObjectName("MenuButton"); b.setFixedSize(84, 28); b.clicked.connect(f)
            b.setStyleSheet("font-size: 11px;")
            bg.addWidget(b, i // 3, i % 3); self.btn_widgets.append((b, img, k))
        self.root.addWidget(bc, 0, Qt.AlignCenter)

        self.guide_label = QLabel(); self.guide_label.setAlignment(Qt.AlignCenter)
        self.guide_label.setStyleSheet("color: #fff; font-size: 9px; font-weight: bold;")
        self.root.addWidget(self.guide_label, 0, Qt.AlignCenter)

        self.apply_theme(self.theme); self._init_tray(app_icon)
        self.retranslate_ui(); self._sync_ui()
        self.ui_timer = QTimer(self); self.ui_timer.timeout.connect(self._sync_ui); self.ui_timer.start(250)
        self.chat_log.append(f"<div style='color:#aaaaaa;'>{self.lang.get('ui.sys_ready')}</div>")

    def on_click_save():
        save_manager.save_now(reason="manual")

    # --- 다국어 및 실시간 번역 ---
    def reset_chat_log(self, reason_key: str = "ui.sys_ready"):
        """채팅 로그 초기화 후 시스템 메시지 1줄 다시 출력"""
        self.chat_log.clear()
        self.chat_log.append(
            f"<div style='color:#aaaaaa;'>{self.lang.get(reason_key)}</div>"
        )

    def _get_localized_mood(self):
        m = self.state.mood
        mk = "v_happy" if m > 80 else "happy" if m > 60 else "normal" if m > 40 else "sad" if m > 20 else "angry"
        return self.lang.get(f"moods.{mk}")

    def retranslate_ui(self):
        L = self.lang
        self.titlebar.title_label.setText(f"{self.state.pet_name} - {L.get('title')}")
        self.guide_label.setText(L.get("ui.guide"))
        for b, _, k in self.btn_widgets: b.setText(L.get(f"buttons.{k}"))
        for k, r in self.status_rows.items(): r[4].setText(L.get(f"status.{k}"))
        if hasattr(self, 'action_open'):
            self.action_open.setText(L.get("ui.tray_open")); self.action_quit.setText(L.get("ui.tray_quit"))

        # ✅ 설정창 열려있으면 설정창도 즉시 번역 반영
        if hasattr(self, "sw") and self.sw is not None and self.sw.isVisible():
            self.sw.retranslate_ui()

    def _sync_ui(self):
        self.money_label.setText(str(int(self.state.money)))
        self.name_label.setText(self.state.pet_name)
        self.mood_label.setText(self._get_localized_mood())
        self.titlebar.title_label.setText(f"{self.state.pet_name} - {self.lang.get('title')}")
        for k, r in self.status_rows.items():
            val = getattr(self.state, k); r[0].setFixedWidth(int((val / 100) * 180)); r[3].setText(f"{int(val)} / 100")

    # --- 테마 및 아이콘 ---
    def apply_theme(self, tn: str):
        self.theme = tn; tp = THEME_BASE_DIR / tn; ud = tp / "ui"; self.current_icon_dir = tp / "icon"
        style = ""
        for p in [THEME_BASE_DIR / "common.qss", tp / f"{tn}.qss"]:
            if p.exists(): style += p.read_text(encoding="utf-8") + "\n"
        tc = "#ffffff" if tn == "dark" else "#703355"

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
        if Path(_p(ud/"panel_chat.png")).exists(): style += f"\n#ChatLog {{ border-image: url('{_p(ud/'panel_chat.png')}') 0 0 0 0 stretch stretch; }}"
        if Path(_p(ud/"panel_status.png")).exists(): style += f"\n#PanelStatus {{ border-image: url('{_p(ud/'panel_status.png')}') 0 0 0 0 stretch stretch; }}"

        # ✅ 패널 + (열려있는) 설정창에 동일 스타일 적용
        self.setStyleSheet(style)
        if hasattr(self, "sw") and self.sw is not None:
            self.sw.setStyleSheet(style)
            self.sw._update_icons()

        self._update_icons()

    def _update_icons(self):
        sys_p = self.current_icon_dir / "ic_main.png"
        if sys_p.exists(): self.titlebar.sys_icon.setPixmap(QPixmap(str(sys_p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        for btn, img in [(self.titlebar.set_btn, "ic_setting.png"), (self.titlebar.min_btn, "ic_min.png"), (self.titlebar.close_btn, "ic_close.png")]:
            p = self.current_icon_dir / img
            if p.exists(): btn.setIcon(QIcon(str(p.resolve()))); btn.setIconSize(QSize(20, 20))
        coin_p = self.current_icon_dir / "ic_coin.png"
        if coin_p.exists(): self.money_icon.setPixmap(QPixmap(str(coin_p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        for k, r in self.status_rows.items():
            p = self.current_icon_dir / r[2]
            if p.exists(): r[1].setPixmap(QPixmap(str(p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        for b, img, _ in self.btn_widgets:
            p = self.current_icon_dir / img
            if not p.exists(): p = app_icon_DIR / img
            if p.exists(): b.setIcon(QIcon(str(p.resolve()))); b.setIconSize(QSize(20, 20))

    # --- 윈도우 관리 및 상호작용 ---
    def _close_all_sub_windows(self, except_win=None):
        for w in [self.home_window, self.job_window, self.study_window]:
            if w and w != except_win and w.isVisible(): w.close()

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
        self._close_all_sub_windows(); is_s, s_e = (self.pet.sleeping, self.pet.sleep_end_at) if self.pet else (False, 0)
        if self.pet: self.pet.hide()
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
        if self.pet: self.pet.hide()
        if self.job_window is None:
            self.job_window = JobWindow(self.state, self.windowIcon())
            orig_c = self.job_window.closeEvent
            self.job_window.closeEvent = lambda e: (self._sync_and_show_main_pet(self.job_window), orig_c(e))
        self.job_window.show(); self.job_window.raise_()

    def open_study(self):
        self._close_all_sub_windows()
        if self.pet: self.pet.hide()
        if self.study_window is None:
            self.study_window = StudyWindow(self.state, self.windowIcon())
            orig_c = self.study_window.closeEvent
            self.study_window.closeEvent = lambda e: (self._sync_and_show_main_pet(self.study_window), orig_c(e))
        self.study_window.show(); self.study_window.raise_()

    def open_settings(self):
        if not hasattr(self, 'sw') or self.sw is None:
            self.sw = SettingsWindow(self.state, self)
            # ✅ 현재 테마/언어 상태를 즉시 반영
            self.sw.sync_from_panel()
        else:
            self.sw.sync_from_panel()

        p = self.geometry().topRight(); self.sw.move(p.x()+10, p.y()); self.sw.show(); self.sw.raise_()

    def _init_tray(self, icon):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self.tray = QSystemTrayIcon(icon if icon else self.windowIcon(), self)
        self.tray_menu = QMenu()
        self.action_open = self.tray_menu.addAction("", lambda: self.show())
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

    def _active_pet_for_chat(self):
        for w in [self.home_window, self.job_window, self.study_window]:
            if w and w.isVisible(): return getattr(w, 'house_pet', getattr(w, 'pet', self.pet))
        return self.pet

    def _format_stat(self, k, v):
        n = self.lang.get(f"status.{k}"); s = "font-size:10px; font-weight:bold;"
        return f"<span style='color:{('#FF5E5E' if v>0 else '#4A90E2')}; {s}'>{'▲' if v>0 else '▼'}{n} {abs(v)}</span>"

    def _delayed_pet_response(self, target, msg, stats, anim):
        sb = f"<br>&nbsp;└ <span style='background:rgba(255,160,209,0.15);'>{stats}</span>" if stats else ""
        self.chat_log.append(f"<div><b>{self.state.pet_name}</b> : {msg}{sb}</div>")
        self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())
        if anim: anim()
        if target: trigger_pet_action_bubble(target, self.chat_log, [msg])

    def handle_interaction(self, uk, logic):
        u_msg = self.lang.get(f"interactions.{uk}_user")
        t = self._active_pet_for_chat(); self.chat_log.append(f"<div style='color:#888;'><b>{self.user_name}</b> : {u_msg}</div>")
        is_s = getattr(t, "sleeping", False) or (hasattr(t, "sleep_end_at") and time.time() < t.sleep_end_at)
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
        self.handle_interaction("feed", f)

    def pet_pet(self):
        def f(t):
            m, f = random.randint(1, 20), random.randint(1, 20); self.state.mood, self.state.fun = clamp(self.state.mood+m), clamp(self.state.fun+f)
            self._delayed_pet_response(t, random.choice(self.lang.get("interactions.chat_pet")), f"{self._format_stat('mood',m)} {self._format_stat('fun',f)}", lambda: t.start_shake(0.4, 2) if hasattr(t, 'start_shake') else t.set_action("jump"))
        self.handle_interaction("chat", f)

    def play_pet(self):
        def f(t):
            e, f, m = -random.randint(1, 20), random.randint(1, 20), random.randint(1, 20); self.state.energy = clamp(self.state.energy+e, 0, 100); self.state.fun, self.state.mood = clamp(self.state.fun+f), clamp(self.state.mood+m)
            def a():
                if hasattr(t, 'do_jump'): t.do_jump(14)
                if self.state.energy < 4 and hasattr(t, 'start_sleep_for_60s'): QTimer.singleShot(1000, t.start_sleep_for_60s)
            self._delayed_pet_response(t, random.choice(self.lang.get("interactions.play_pet")), f"{self._format_stat('energy',e)} {self._format_stat('fun',f)} {self._format_stat('mood',m)}", a)
        self.handle_interaction("play", f)

# -------------------------
# 4. 설정 창
# -------------------------
class SettingsWindow(StyledWidget):
    # ✅ 컨트롤 패널(300x380)보다 작게, 비율 유지해서 고정
    BASE_W, BASE_H = 300, 420
    SCALE = 0.90
    WIN_W = int(BASE_W * SCALE)   # 270
    WIN_H = int(BASE_H * SCALE)   # 378

    def __init__(self, state, panel: ControlPanel):
        super().__init__()
        self.state, self.panel = state, panel
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.WIN_W, self.WIN_H)
        self.setObjectName("SettingsWindow")

        # ✅ WindowFrame + TitleBar로 구성해서 테마 에셋(QSS) 적용되게
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        self.frame = StyledWidget(self); self.frame.setObjectName("WindowFrame")
        outer.addWidget(self.frame)

        frame_lay = QVBoxLayout(self.frame); frame_lay.setContentsMargins(0, 0, 0, 0); frame_lay.setSpacing(0)

        self.titlebar = SettingsTitleBar(self.frame, self)
        frame_lay.addWidget(self.titlebar)

        content = QWidget(self.frame)
        frame_lay.addWidget(content, 1)

        # 내부 여백은 창이 작아졌으니 살짝만 줄임
        pad = int(20 * self.SCALE)
        lay = QVBoxLayout(content); lay.setContentsMargins(pad, pad - 2, pad, pad); lay.setSpacing(int(10 * self.SCALE))

        # ---- UI ----
        self.tl = QLabel()
        self.tl.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        lay.addWidget(self.tl)

        self.ul = QLabel(); lay.addWidget(self.ul)
        self.ui = QTextEdit(); self.ui.setFixedHeight(int(30 * self.SCALE)); self.ui.setText(panel.user_name)
        lay.addWidget(self.ui)

        self.pl = QLabel(); lay.addWidget(self.pl)
        self.pi = QTextEdit(); self.pi.setFixedHeight(int(30 * self.SCALE)); self.pi.setText(state.pet_name)
        lay.addWidget(self.pi)

        # ✅ 테마: 드롭박스
        self.thl = QLabel(); lay.addWidget(self.thl)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["pink", "dark"])
        self.theme_combo.setCurrentText(self.panel.theme)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        lay.addWidget(self.theme_combo)

        # ✅ 언어: 버튼 2개 (한국어/English)
        self.ll = QLabel(); lay.addWidget(self.ll)
        lang_row = QHBoxLayout()
        lang_row.setSpacing(int(8 * self.SCALE))

        self.lang_ko_btn = QPushButton()
        self.lang_en_btn = QPushButton()
        for b in (self.lang_ko_btn, self.lang_en_btn):
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(int(34 * self.SCALE))
            b.setStyleSheet("""
                QPushButton {
                    border-radius: 10px;
                    padding: 6px 10px;
                    border: 1px solid rgba(255,255,255,90);
                    background: rgba(0,0,0,35);
                    color: white;
                    font-weight: 800;
                }
                QPushButton:checked {
                    background: rgba(255,160,209,80);
                    border: 1px solid rgba(255,255,255,150);
                }
            """)

        self.lang_ko_btn.clicked.connect(lambda: self._select_lang("ko"))
        self.lang_en_btn.clicked.connect(lambda: self._select_lang("en"))

        lang_row.addWidget(self.lang_ko_btn, 1)
        lang_row.addWidget(self.lang_en_btn, 1)
        lay.addLayout(lang_row)

        lay.addStretch(1)

        self.sb = QPushButton()
        self.sb.setFixedHeight(int(36 * self.SCALE))
        self.sb.clicked.connect(self.save)
        lay.addWidget(self.sb)

        # 상태값
        self._selected_lang = self.panel.lang.lang_code
        self.sync_from_panel()
        self.retranslate_ui()

        # ✅ 테마(QSS)도 패널과 동일하게(열릴 때 즉시)
        self.setStyleSheet(self.panel.styleSheet())
        self._update_icons()

    # -------------------------
    # sync / i18n
    # -------------------------
    def sync_from_panel(self):
        """패널의 현재 테마/언어 상태를 설정창 UI에 동기화"""
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(self.panel.theme)
        self.theme_combo.blockSignals(False)

        self._selected_lang = self.panel.lang.lang_code
        self._apply_lang_btn_state()

        # 이름 입력칸도 패널/상태 기준으로 다시 채워줌(이미 열려있는 동안 바뀐 경우 대응)
        self.ui.setText(self.panel.user_name)
        self.pi.setText(self.state.pet_name)

        self.retranslate_ui()
        self._update_icons()

    def _apply_lang_btn_state(self):
        self.lang_ko_btn.setChecked(self._selected_lang == "ko")
        self.lang_en_btn.setChecked(self._selected_lang == "en")

    def _select_lang(self, code: str):
        self._selected_lang = code
        self._apply_lang_btn_state()
        # ✅ 저장 전에도 “설정창 내부” 텍스트만 미리 바꿔 보여주고 싶으면,
        # 패널 lang를 건드리면 전체 UI가 바뀌어버리니까 여기서는 안 건드림.

    def retranslate_ui(self):
        L = self.panel.lang
        self.titlebar.title_label.setText(L.get("ui.settings"))
        self.tl.setText(L.get("ui.settings"))
        self.ul.setText(L.get("ui.user_name"))
        self.pl.setText(L.get("ui.pet_name"))
        self.thl.setText(L.get("ui.theme"))
        self.ll.setText(L.get("ui.lang"))
        self.sb.setText(L.get("ui.save"))

        # 버튼 텍스트는 고정 요구(한국어/영어)라서 그대로, 대신 현재 언어에 따라 약간 자연스럽게:
        # - panel.lang이 ko/en 어떤 상태든 버튼에는 "한국어", "English" 그대로 박아둠
        self.lang_ko_btn.setText("한국어")
        self.lang_en_btn.setText("English")

    def _on_theme_changed(self, theme_name: str):
        # ✅ 즉시 미리보기(패널/설정창 같이 테마 적용)
        if theme_name and theme_name != self.panel.theme:
            self.panel.apply_theme(theme_name)
            # apply_theme 내부에서 self.sw 스타일도 동기화함

    def _update_icons(self):
        # titlebar 아이콘/닫기 아이콘 패널 테마와 동일하게
        icon_dir = getattr(self.panel, "current_icon_dir", None)
        if not icon_dir:
            return

        sys_p = icon_dir / "ic_main.png"
        if sys_p.exists():
            self.titlebar.sys_icon.setPixmap(
                QPixmap(str(sys_p.resolve())).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        close_p = icon_dir / "ic_close.png"
        if close_p.exists():
            self.titlebar.close_btn.setIcon(QIcon(str(close_p.resolve())))
            self.titlebar.close_btn.setIconSize(QSize(20, 20))

    # -------------------------
    # save
    # -------------------------
    def save(self):
        u = self.ui.toPlainText().strip()
        p = self.pi.toPlainText().strip()
        l = self._selected_lang

        if u:
            self.panel.user_name = u
        if p:
            self.state.pet_name = p

        # ✅ 언어 변경
        if l != self.panel.lang.lang_code:
            self.panel.lang.load_lang(l)
            if self.panel.user_name in ["나", "Me"]:
                self.panel.user_name = self.panel.lang.get("user_name")
            if self.state.pet_name in ["라이미", "Raimi"]:
                self.state.pet_name = self.panel.lang.get("pet_name")

            # 패널 전체 번역 반영(+ 설정창도)
            self.panel.retranslate_ui()
            self.retranslate_ui()

            self.panel.reset_chat_log("ui.sys_ready")
        

        self.panel._sync_ui()
        self.close()