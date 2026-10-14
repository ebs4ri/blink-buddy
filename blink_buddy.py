#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blink Buddy · Dry Eye (dryeye.dk)

Et lille, roligt øje, der ligger forrest på skærmen og blinker. Med faste
mellemrum kommer en stille påmindelse: "Blink helt 5 gange". Udviklet som
velværeværktøj til mennesker med tørre øjne og skærmarbejde. Ikke medicinsk udstyr.

Kør:      python blink_buddy.py
Byg:      build_windows_exe.bat (Windows) eller build_mac_app.sh (Mac)
"""

from __future__ import annotations

import math
import os
import random
import sys
import webbrowser

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRect, QRectF, QSettings, QSize, Qt, QTimer,
                            QVariantAnimation)
from PySide6.QtGui import (QAction, QBrush, QColor, QCursor, QFont, QGuiApplication, QIcon, QImage, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QMenu, QPushButton, QSpinBox, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

ORG_NAME = "Dry Eye"
APP_NAME = "Blink Buddy"
APP_VERSION = "1.1.0"
URL_DRYEYE = "https://dryeye.dk"
URL_REDSYNET = "https://www.eyerescue.net/da/"

# Dry Eye-paletten (samme som dryeye.dk)
C_NAVY = QColor("#162A3B")
C_TEAL = QColor("#3C766D")
C_TEAL_DEEP = QColor("#2A5A52")
C_TEAL_TINT = QColor("#E3ECE5")
C_SAND = QColor("#F7F1E4")
C_CREAM = QColor("#FBF7EC")
C_INK_SOFT = QColor("#4A5B6B")

# Standardindstillinger
DEF_BLINK_SEC = 5          # øjets eget blink, sekunder (±20 % variation)
DEF_REMIND_MIN = 15        # påmindelse hvert ... minut
DEF_SHOW_SEC = 6           # påmindelsen vises i ... sekunder (tid nok til 5 hele blink)
BLINK_MS_MIN, BLINK_MS_MAX = 150, 230

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_FROZEN = getattr(sys, "frozen", False)
MAC_BUNDLE_ID = "dk.dryeye.blinkbuddy"

# Hvor påmindelsen vises. "eye" = ved øjet, "custom" = hvor brugeren selv har trukket den hen.
REMIND_POSITIONS = [("eye", "Ved øjet"), ("custom", "Hvor jeg selv har placeret den (træk i boksen)"),
                    ("center", "Midt på skærmen"), ("tl", "Øverst til venstre"), ("tr", "Øverst til højre"),
                    ("bl", "Nederst til venstre"), ("br", "Nederst til højre")]
LOOKS = [("eye", "Øje"), ("logo", "Dry Eye-logo")]


# ----------------------------------------------------------------------------- tegning af øjet
# Referencesystem 1024 x 1024, efter Dry Eyes designskitse: ingen sclera, to bløde,
# tilspidsede låg (øvre mørk teal, nedre lys blågrå), stor iris med striber, mørk
# pupil og ét stort hvidt højlys øverst til højre.
def _curve_path(P, segs):
    """segs: liste af punkter; første er start, derefter grupper af 3 (c1, c2, slut)."""
    path = QPainterPath()
    path.moveTo(P(*segs[0]))
    for i in range(1, len(segs) - 2, 3):
        path.cubicTo(P(*segs[i]), P(*segs[i + 1]), P(*segs[i + 2]))
    return path


def _mirror(pts):
    return [(1024 - x, y) for (x, y) in pts]


# Lågenes kanter, venstre halvdel, i referencesystemet (højre halvdel spejles).
# Øvre låg: tilspidset med et lille nedadgående "hook" i øjenkrogen.
UP_TOP_L = [(18, 543), (40, 522), (120, 430), (250, 352), (360, 300), (440, 296), (512, 296)]
UP_BOT_L = [(512, 352), (380, 362), (250, 430), (140, 500), (95, 522), (50, 536), (18, 543)]
# Nedre låg: lys, tyndere, med spidser der løfter sig mod øjenkrogen.
LO_BOT_L = [(92, 590), (150, 640), (270, 760), (400, 796), (450, 806), (490, 804), (512, 804)]
LO_TOP_L = [(512, 752), (420, 750), (300, 712), (200, 655), (150, 626), (115, 604), (92, 590)]


def _lid(P, top_l, bot_l, fy=lambda x, y: y):
    """Lukket flade: top-kant venstre→højre, bund-kant højre→venstre."""
    top = top_l + [(1024 - x, y) for (x, y) in reversed(top_l[:-1])]
    bot_r = [(1024 - x, y) for (x, y) in reversed(bot_l)]      # højre: midt → spids
    bot = bot_r[:] + bot_l[1:]
    pts = [(x, fy(x, y)) for (x, y) in top] + [(x, fy(x, y)) for (x, y) in bot[1:]]
    path = QPainterPath()
    path.moveTo(P(*pts[0]))
    for i in range(1, len(pts) - 2, 3):
        path.cubicTo(P(*pts[i]), P(*pts[i + 1]), P(*pts[i + 2]))
    path.closeSubpath()
    return path


_FRAMES = None   # (åbent, halvt, lukket) som QPixmap, eller False hvis filerne mangler
FRAME_W, FRAME_H = 708, 378   # billedernes mål (bredde/højde-forhold 1,873)


def _load_frames():
    """Dry Eyes tre øjebilleder (frames/eye-open/half/closed.png). Indlæses én gang."""
    global _FRAMES
    if _FRAMES is None:
        pms = []
        for n in ("open", "half", "closed"):
            pm = QPixmap(resource_path(os.path.join("frames", f"eye-{n}.png")))
            if pm.isNull():
                _FRAMES = False
                return _FRAMES
            pms.append(pm)
        _FRAMES = tuple(pms)
    return _FRAMES


def paint_eye(p: QPainter, rect: QRectF, closed: float, aura: bool = False) -> None:
    """Tegner øjet i rect. closed: 0 = åbent, 1 = lukket."""
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    frames = _load_frames()
    if frames:
        c = max(0.0, min(1.0, closed))
        # Billedet lægges midt i rect med samme bredde (øjet fylder 1024/1024 i bredden)
        w = rect.width()
        h = w * FRAME_H / FRAME_W
        target = QRectF(rect.left(), rect.top() + (rect.height() - h) / 2.0 + rect.height() * 0.04, w, h)
        if aura:
            g = QRadialGradient(target.center(), w * 0.55)
            g.setColorAt(0.0, QColor(251, 247, 236, 120))
            g.setColorAt(0.6, QColor(251, 247, 236, 50))
            g.setColorAt(1.0, QColor(251, 247, 236, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(target.center(), w * 0.55, h * 0.75)
        # Tre faser som i designskitsen: åbent -> halvt -> lukket. Skift sker som klip
        # (ingen overtoning), så lågene aldrig ligger dobbelt.
        if c < 0.3:
            fr = frames[0]
        elif c < 0.72:
            fr = frames[1]
        else:
            fr = frames[2]
        p.drawPixmap(target, fr, QRectF(fr.rect()))
        return
    _paint_eye_drawn(p, rect, closed, aura)


def _paint_eye_drawn(p: QPainter, rect: QRectF, closed: float, aura: bool = False) -> None:
    """Reserve: tegnet øje (bruges kun hvis billedfilerne mangler)."""
    s = rect.width() / 1024.0
    ox, oy = rect.left(), rect.top()

    def P(x, y):
        return QPointF(ox + x * s, oy + y * s)

    c = max(0.0, min(1.0, closed))
    dU = 360 * c

    def wU(x):
        d = (x - 512) / 496.0
        return 0.25 + 0.75 * (1.0 - d * d)

    def fU(x, y):
        return y + dU * wU(x)

    dL = 50 * c

    def fL(x, y):
        d = (x - 512) / 420.0
        return y - dL * max(0.0, 1.0 - d * d)

    if aura:
        g = QRadialGradient(P(512, 560), 560 * s)
        g.setColorAt(0.0, QColor(251, 247, 236, 120))
        g.setColorAt(0.6, QColor(251, 247, 236, 50))
        g.setColorAt(1.0, QColor(251, 247, 236, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(P(512, 560), 560 * s, 360 * s)

    # Åbningen: under øvre lågs underkant og over nedre lågs overkant
    up_bot_full = UP_BOT_L[::-1]                                  # spids → midt (venstre)
    up_bot_full = up_bot_full + [(1024 - x, y) for (x, y) in reversed(up_bot_full[:-1])]
    lo_top_full = LO_TOP_L[::-1]                                  # spids → midt (venstre)
    lo_top_full = lo_top_full + [(1024 - x, y) for (x, y) in reversed(lo_top_full[:-1])]
    opening = QPainterPath()
    pts = [(x, fU(x, y)) for (x, y) in up_bot_full]
    opening.moveTo(P(*pts[0]))
    for i in range(1, len(pts) - 2, 3):
        opening.cubicTo(P(*pts[i]), P(*pts[i + 1]), P(*pts[i + 2]))
    pts2 = [(x, fL(x, y)) for (x, y) in reversed(lo_top_full)]   # højre spids → venstre spids
    opening.lineTo(P(*pts2[0]))
    for i in range(1, len(pts2) - 2, 3):
        opening.cubicTo(P(*pts2[i]), P(*pts2[i + 1]), P(*pts2[i + 2]))
    opening.closeSubpath()

    cx, cy, ir = 512, 549, 176
    if c < 0.97:
        p.save()
        p.setClipPath(opening)
        gi = QRadialGradient(P(cx, cy), ir * s)
        gi.setColorAt(0.0, QColor("#C9E0E2"))
        gi.setColorAt(0.45, QColor("#9CC3C7"))
        gi.setColorAt(0.8, QColor("#6FA2A8"))
        gi.setColorAt(1.0, QColor("#4A7D83"))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(gi))
        p.drawEllipse(P(cx, cy), ir * s, ir * s)
        # fine striber
        pen = QPen(QColor(255, 255, 255, 46), max(0.8, 2.2 * s))
        p.setPen(pen)
        for k in range(40):
            a = k * (2 * math.pi / 40) + 0.07
            r1 = 86 + (k % 3) * 10
            p.drawLine(QPointF(ox + (cx + math.cos(a) * r1) * s, oy + (cy + math.sin(a) * r1) * s),
                       QPointF(ox + (cx + math.cos(a) * 168) * s, oy + (cy + math.sin(a) * 168) * s))
        pen2 = QPen(QColor(40, 90, 96, 40), max(0.8, 2.2 * s))
        p.setPen(pen2)
        for k in range(40):
            a = k * (2 * math.pi / 40) + 0.15
            p.drawLine(QPointF(ox + (cx + math.cos(a) * 95) * s, oy + (cy + math.sin(a) * 95) * s),
                       QPointF(ox + (cx + math.cos(a) * 172) * s, oy + (cy + math.sin(a) * 172) * s))
        # pupil med blød kant
        p.setPen(Qt.NoPen)
        gp = QRadialGradient(P(cx, cy), 80 * s)
        gp.setColorAt(0.0, QColor("#2A4650"))
        gp.setColorAt(0.9, QColor("#253F46"))
        gp.setColorAt(1.0, QColor(37, 63, 70, 0))
        p.setBrush(QBrush(gp))
        p.drawEllipse(P(cx, cy), 80 * s, 80 * s)
        # højlys
        gh = QRadialGradient(P(594, 463), 40 * s)
        gh.setColorAt(0.0, QColor(255, 255, 255, 240))
        gh.setColorAt(0.85, QColor(236, 246, 246, 215))
        gh.setColorAt(1.0, QColor(236, 246, 246, 0))
        p.setBrush(QBrush(gh))
        p.drawEllipse(P(594, 463), 40 * s, 40 * s)
        p.restore()

    # Nedre låg (lys blågrå, tilspidset)
    p.setPen(Qt.NoPen)
    gl = QRadialGradient(P(512, 760), 520 * s)
    gl.setColorAt(0.0, QColor("#C6DCDE"))
    gl.setColorAt(1.0, QColor("#9DBFC3"))
    p.setBrush(QBrush(gl))
    p.drawPath(_lid(P, LO_TOP_L[::-1], LO_BOT_L[::-1], fL))
    # Øvre låg (mørk teal, tilspidset med hook i øjenkrogen)
    gu = QRadialGradient(P(512, 330), 640 * s)
    gu.setColorAt(0.0, QColor("#4F8389"))
    gu.setColorAt(1.0, QColor("#3B6A70"))
    p.setBrush(QBrush(gu))
    p.drawPath(_lid(P, UP_TOP_L, UP_BOT_L, fU))


_LOGO = None


def _load_logo():
    global _LOGO
    if _LOGO is None:
        pm = QPixmap(resource_path(os.path.join("frames", "logo-mark.png")))
        _LOGO = pm if not pm.isNull() else False
    return _LOGO


# Logoets "låg" fra dryeye.dk: øjets omrids i logoets koordinater (261 x 265). Ved blink
# skaleres det sorte låg ned over øjet fra oven, præcis som på forsiden.
LOGO_LID = [(133.2, 120.5), (131.5, 122.5), (128.9, 124.5), (127.7, 126.5), (120.1, 128.5), (110.9, 130.5), (104.1, 132.5), (101.7, 134.5), (100.3, 136.5), (99.3, 138.5), (98.7, 140.5), (98.5, 142.5), (98.9, 144.5), (99.7, 146.5), (100.7, 148.5), (101.9, 150.5), (103.5, 152.5), (105.5, 154.5), (107.5, 156.5), (109.7, 158.5), (111.8, 160.5), (135.2, 161.5), (137.3, 159.5), (140.9, 157.5), (143.5, 155.5), (145.5, 153.5), (147.5, 151.5), (149.3, 149.5), (150.5, 147.5), (151.3, 145.5), (152.1, 143.5), (152.5, 141.5), (152.5, 139.5), (152.5, 137.5), (152.5, 135.5), (152.5, 133.5), (152.5, 131.5), (152.5, 129.5), (152.5, 127.5), (152.1, 125.5), (151.1, 123.5), (149.5, 121.5)]


def paint_logo(p: QPainter, rect: QRectF, closed: float) -> None:
    """Dry Eye-logoet (tigerøjet). Ved blink lukker et sort låg ned over øjet, som på forsiden af dryeye.dk."""
    logo = _load_logo()
    if not logo:
        paint_eye(p, rect, closed)
        return
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    s = min(rect.width() / 261.0, rect.height() / 265.0)
    w, h = 261 * s, 265 * s
    target = QRectF(rect.left() + (rect.width() - w) / 2, rect.top() + (rect.height() - h) / 2, w, h)
    p.drawPixmap(target, logo, QRectF(logo.rect()))
    c = max(0.0, min(1.0, closed))
    if c <= 0.01:
        return
    top = min(y for _, y in LOGO_LID)
    lid = QPainterPath()
    for i, (x, y) in enumerate(LOGO_LID):
        # skaleres lodret fra lågets overkant (som transform-origin 50% 0 på forsiden)
        yy = top + (y - top) * c
        pt = QPointF(target.left() + x * s, target.top() + yy * s)
        if i == 0:
            lid.moveTo(pt)
        else:
            lid.lineTo(pt)
    lid.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#000000"))
    p.drawPath(lid)


def logo_pixmap(size: int) -> QPixmap:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    paint_logo(p, QRectF(0, 0, size, size), 0.0)
    p.end()
    return QPixmap.fromImage(img)


def eye_pixmap(size: int, closed: float = 0.0, aura: bool = False) -> QPixmap:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    paint_eye(p, QRectF(0, -size * 0.04, size, size), closed, aura=aura)
    p.end()
    return QPixmap.fromImage(img)


def generate_icon(path: str) -> None:
    """Laver et .ico/.png-ikon med Pillow ud fra Qt-tegningen (uden tekst, uden kasse)."""
    try:
        from PIL import Image
    except Exception:
        return
    sizes = [256, 128, 64, 48, 32, 16]
    frames = []
    for n in sizes:
        pm = eye_pixmap(n, 0.0, aura=False)
        img = pm.toImage().convertToFormat(QImage.Format_RGBA8888)
        buf = bytes(img.constBits())
        frames.append(Image.frombytes("RGBA", (n, n), buf))
    frames[0].save(path, format="ICO", sizes=[(n, n) for n in sizes], append_images=frames[1:])


def generate_icns(path: str) -> None:
    """Mac-ikon (.icns) ud fra det åbne øje. Bruges af byggescriptet på macOS."""
    try:
        from PIL import Image
    except Exception:
        return
    n = 1024
    pm = eye_pixmap(n, 0.0, aura=False)
    img = pm.toImage().convertToFormat(QImage.Format_RGBA8888)
    im = Image.frombytes("RGBA", (n, n), bytes(img.constBits()))
    im.save(path, format="ICNS")


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ----------------------------------------------------------------------------- autostart (Windows)
def autostart_supported() -> bool:
    return IS_FROZEN and (IS_WINDOWS or IS_MAC)


def _mac_agent_path() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{MAC_BUNDLE_ID}.plist")


def autostart_get() -> bool:
    if not autostart_supported():
        return False
    if IS_MAC:
        return os.path.exists(_mac_agent_path())
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except Exception:
        return False


def autostart_set(on: bool) -> None:
    if not autostart_supported():
        return
    if IS_MAC:
        try:
            path = _mac_agent_path()
            if on:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                exe = sys.executable
                plist = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{MAC_BUNDLE_ID}</string>
  <key>ProgramArguments</key><array><string>{exe}</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
'''
                with open(path, "w", encoding="utf-8") as f:
                    f.write(plist)
            elif os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
    except Exception:
        pass


# ----------------------------------------------------------------------------- påmindelse
class ReminderPopup(QWidget):
    """Lille, rolig boks: 'Blink helt 5 gange' med nedtælling. Én fast instans, der vises
    og skjules. Kan trækkes med musen; så huskes stedet. Klik lukker den."""

    def __init__(self, owner: "BlinkBuddy"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        if IS_MAC:
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        self.owner = owner
        self.total = DEF_SHOW_SEC
        self.count = 5
        self.alpha = 1.0
        self.drag_offset = None
        self.moved = False
        self.setFixedSize(300, 112)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.fade = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=260)
        self.fade.valueChanged.connect(self._set_alpha)
        self.out = QVariantAnimation(self, startValue=1.0, endValue=0.0, duration=320)
        self.out.valueChanged.connect(self._set_alpha)
        self.out.finished.connect(self.hide)

    # --- vis / skjul
    def start(self, seconds: int):
        self.out.stop()
        self.total = max(3, seconds)
        self.count = 5
        self.moved = False
        self.place()
        self.timer.start(int(self.total * 1000 / 5))
        self.alpha = 0.0
        self.show()
        self.raise_()
        self.fade.start()
        self.update()

    def dismiss(self):
        self.timer.stop()
        self.fade.stop()
        self.out.stop()
        self.hide()

    def _set_alpha(self, v):
        self.alpha = float(v)
        self.update()

    def place(self):
        """Placerer boksen efter indstillingen remind_pos (se REMIND_POSITIONS)."""
        s = self.owner.s
        mode = s.value("remind_pos", "eye")
        w = self.owner
        screen = w.screen() or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        W, H = self.width(), self.height()
        m = 24
        if mode == "custom":
            x = s.value("remind_x", None); y = s.value("remind_y", None)
            if x is not None and y is not None:
                pos = QPoint(int(x), int(y))
                if any(sc.availableGeometry().contains(QRect(pos, self.size()).center()) for sc in QGuiApplication.screens()):
                    self.move(pos)
                    return
            mode = "eye"
        if mode == "center":
            self.move(g.center().x() - W // 2, g.center().y() - H // 2)
        elif mode == "tl":
            self.move(g.left() + m, g.top() + m)
        elif mode == "tr":
            self.move(g.right() - W - m, g.top() + m)
        elif mode == "bl":
            self.move(g.left() + m, g.bottom() - H - m)
        elif mode == "br":
            self.move(g.right() - W - m, g.bottom() - H - m)
        else:  # ved øjet
            x = w.x() + w.width() // 2 - W // 2
            y = w.y() - H - 10
            if y < g.top():
                y = w.y() + w.height() + 10
            x = min(max(x, g.left() + 8), g.right() - W - 8)
            self.move(x, y)

    def _tick(self):
        self.count -= 1
        self.owner.blink(False)   # øjet blinker med i takt med nedtællingen
        if self.count <= 0:
            self.timer.stop()
            self.out.start()
        self.update()

    # --- mus: klik lukker, træk flytter og husker stedet
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.moved = False

    def mouseMoveEvent(self, e):
        if self.drag_offset is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_offset)
            self.moved = True

    def mouseReleaseEvent(self, e):
        if self.drag_offset is None:
            return
        self.drag_offset = None
        if self.moved:
            self.owner.s.setValue("remind_pos", "custom")
            self.owner.s.setValue("remind_x", self.x()); self.owner.s.setValue("remind_y", self.y())
            self.timer.start(int(self.total * 1000 / 5))   # giv lidt ekstra tid efter flytning
        else:
            self.dismiss()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setOpacity(self.alpha)
        r = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        # flade i samme farve som det øvre øjenlåg
        g = QRadialGradient(QPointF(r.left() + r.width() * 0.3, r.top()), r.width() * 1.1)
        g.setColorAt(0.0, QColor("#4F8389"))
        g.setColorAt(1.0, QColor("#3B6A70"))
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 18, 18)
        # tekst
        p.setPen(QColor("#FFFFFF"))
        f = QFont()
        f.setFamily("Segoe UI" if IS_WINDOWS else "Helvetica")
        f.setPointSize(14)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(r.left() + 18, r.top() + 14, r.width() - 90, 30), Qt.AlignLeft | Qt.AlignVCenter, "Blink 5 gange")
        f2 = QFont(f)
        f2.setPointSize(10)
        f2.setBold(False)
        p.setFont(f2)
        p.setPen(QColor(255, 255, 255, 225))
        p.drawText(QRectF(r.left() + 18, r.top() + 46, r.width() - 90, 24), Qt.AlignLeft | Qt.AlignVCenter, "Luk øjnene helt og roligt.")
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(QRectF(r.left() + 18, r.top() + 68, r.width() - 90, 24), Qt.AlignLeft | Qt.AlignVCenter, "Dry Eye")
        # nedtælling i lys cirkel
        cx, cy, rad = r.right() - 40, r.center().y(), 26
        p.setPen(Qt.NoPen)
        p.setBrush(C_CREAM)
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        f3 = QFont(f)
        f3.setPointSize(16)
        p.setFont(f3)
        p.setPen(QColor("#3B6A70"))
        p.drawText(QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad), Qt.AlignCenter, str(max(1, self.count)))


# ----------------------------------------------------------------------------- indstillinger
class SettingsDialog(QDialog):
    def __init__(self, s: QSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} · Indstillinger")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.s = s
        lay = QVBoxLayout(self)
        intro = QLabel("Øjet blinker af sig selv og minder dig om at blinke helt med faste mellemrum.\n"
                       "Træk øjet med musen. Højreklik for menu.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.blink = QSpinBox(); self.blink.setRange(2, 30); self.blink.setSuffix(" s")
        self.blink.setValue(int(s.value("blink_sec", DEF_BLINK_SEC)))
        self.remind = QSpinBox(); self.remind.setRange(1, 120); self.remind.setSuffix(" min")
        self.remind.setValue(int(s.value("remind_min", DEF_REMIND_MIN)))
        self.show_s = QSpinBox(); self.show_s.setRange(3, 20); self.show_s.setSuffix(" s")
        self.show_s.setValue(int(s.value("show_sec", DEF_SHOW_SEC)))
        self.look = QComboBox()
        for key, label in LOOKS:
            self.look.addItem(label, key)
        self.look.setCurrentIndex(max(0, [k for k, _ in LOOKS].index(s.value("look", "eye")) if s.value("look", "eye") in [k for k, _ in LOOKS] else 0))
        self.pos = QComboBox()
        for key, label in REMIND_POSITIONS:
            self.pos.addItem(label, key)
        cur = s.value("remind_pos", "eye")
        keys = [k for k, _ in REMIND_POSITIONS]
        self.pos.setCurrentIndex(keys.index(cur) if cur in keys else 0)
        form.addRow("Udseende", self.look)
        form.addRow("Øjets blinkinterval", self.blink)
        form.addRow("Påmindelse hvert", self.remind)
        form.addRow("Påmindelsen vises i", self.show_s)
        form.addRow("Påmindelsen vises", self.pos)
        lay.addLayout(form)
        hint = QLabel("Påmindelsen kan altid trækkes med musen til et andet sted; så huskes det.")
        hint.setWordWrap(True); hint.setStyleSheet("color:#78879A; font-size:11px;")
        lay.addWidget(hint)
        self.preview_btn = QPushButton("Vis påmindelsen nu")
        lay.addWidget(self.preview_btn)
        self.autostart = QCheckBox("Start automatisk, når computeren starter")
        self.autostart.setChecked(autostart_get())
        self.autostart.setEnabled(autostart_supported())
        if not autostart_supported():
            self.autostart.setToolTip("Kun i den installerede Windows- eller Mac-udgave.")
        lay.addWidget(self.autostart)
        self.brand = QCheckBox("Vis 'dryeye.dk' under øjet")
        self.brand.setChecked(s.value("brand", "1") == "1")
        lay.addWidget(self.brand)
        links = QHBoxLayout()
        b1 = QPushButton("Åbn dryeye.dk"); b1.clicked.connect(lambda: webbrowser.open(URL_DRYEYE))
        b2 = QPushButton("Støt Red Synet"); b2.clicked.connect(lambda: webbrowser.open(URL_REDSYNET))
        links.addWidget(b1); links.addWidget(b2)
        lay.addLayout(links)
        note = QLabel(f"{APP_NAME} {APP_VERSION} · Dry Eye. Velværeværktøj, ikke medicinsk udstyr.")
        note.setStyleSheet("color:#78879A; font-size:11px;")
        lay.addWidget(note)
        bb = QDialogButtonBox()
        ok = bb.addButton("Gem", QDialogButtonBox.AcceptRole)
        cancel = bb.addButton("Annuller", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.setStyleSheet("QDialog{background:#FBF7EC;} QLabel{color:#162A3B;} QPushButton{padding:6px 12px;}")

    def save(self):
        self.s.setValue("blink_sec", self.blink.value())
        self.s.setValue("remind_min", self.remind.value())
        self.s.setValue("show_sec", self.show_s.value())
        self.s.setValue("look", self.look.currentData())
        self.s.setValue("remind_pos", self.pos.currentData())
        self.s.setValue("brand", "1" if self.brand.isChecked() else "0")
        autostart_set(self.autostart.isChecked())


# ----------------------------------------------------------------------------- selve øjet
class BlinkBuddy(QWidget):
    W, H = 220, 150

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        if IS_MAC:
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        self.setFixedSize(self.W, self.H)
        self.setWindowTitle(APP_NAME)
        self.s = QSettings(ORG_NAME, APP_NAME)
        self.closed = 0.0
        self.paused_until = None
        self.drag_offset = None
        self.popup = ReminderPopup(self)
        self.setToolTip("Blink Buddy · Dry Eye. Træk med musen, højreklik for menu.")

        # blink-animation
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0)
        self.anim.setEasingCurve(QEasingCurve.InOutSine)
        self.anim.valueChanged.connect(self._on_anim)
        self.anim.finished.connect(self._after_blink)
        self.blink_timer = QTimer(self); self.blink_timer.setSingleShot(True)
        self.blink_timer.timeout.connect(self.blink)
        self.remind_timer = QTimer(self); self.remind_timer.setSingleShot(True)
        self.remind_timer.timeout.connect(self.remind)

        self._restore_position()
        self._schedule_blink()
        self._schedule_reminder()
        self._setup_tray()
        if self.s.value("first_run", "1") == "1":
            QTimer.singleShot(900, self._first_run_hint)
            self.s.setValue("first_run", "0")

    # --- indstillinger
    def blink_sec(self): return int(self.s.value("blink_sec", DEF_BLINK_SEC))
    def remind_min(self): return int(self.s.value("remind_min", DEF_REMIND_MIN))
    def show_sec(self): return int(self.s.value("show_sec", DEF_SHOW_SEC))
    def look(self): return "logo" if self.s.value("look", "eye") == "logo" else "eye"

    # --- position
    def _restore_position(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = self.s.value("x", None); y = self.s.value("y", None)
        pos = None
        if x is not None and y is not None:
            pos = QPoint(int(x), int(y))
            ok = any(sc.availableGeometry().contains(QRect(pos, self.size()).center()) for sc in QGuiApplication.screens())
            if not ok:
                pos = None
        if pos is None:
            pos = QPoint(screen.right() - self.W - 24, screen.bottom() - self.H - 48)
        self.move(pos)

    def _save_position(self):
        self.s.setValue("x", self.x()); self.s.setValue("y", self.y())

    # --- blink
    def _schedule_blink(self):
        base = self.blink_sec() * 1000
        ms = int(base * random.uniform(0.8, 1.2))
        self.blink_timer.start(ms)

    def blink(self, double: bool | None = None):
        if self.anim.state() == QVariantAnimation.Running:
            return
        self._double = random.random() < 0.12 if double is None else double
        self.anim.setDuration(random.randint(BLINK_MS_MIN, BLINK_MS_MAX))
        self.anim.setDirection(QVariantAnimation.Forward)
        self.anim.start()

    def _on_anim(self, v):
        self.closed = float(v)
        self.update()

    def _after_blink(self):
        if self.anim.direction() == QVariantAnimation.Forward:
            self.anim.setDirection(QVariantAnimation.Backward)
            self.anim.start()
            return
        if getattr(self, "_double", False):
            self._double = False
            QTimer.singleShot(120, lambda: self.blink(False))
            return
        self._schedule_blink()

    # --- påmindelse
    def _schedule_reminder(self):
        self.remind_timer.start(self.remind_min() * 60 * 1000)

    def remind(self):
        if self.paused_until is not None:
            from datetime import datetime
            if datetime.now() < self.paused_until:
                self._schedule_reminder()
                return
            self.paused_until = None
            self._update_tray_pause()
        self.show_reminder()
        self._schedule_reminder()

    def show_reminder(self):
        """Viser påmindelsen (bruges også fra menu og indstillinger)."""
        self.popup.start(self.show_sec())
        self.blink(False)

    def pause(self, hours: float):
        from datetime import datetime, timedelta
        self.paused_until = datetime.now() + timedelta(hours=hours)
        self._update_tray_pause()

    def resume(self):
        self.paused_until = None
        self._update_tray_pause()
        self._schedule_reminder()

    # --- bakke-ikon og menu
    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip(f"{APP_NAME} · Dry Eye")
        self.tray.setContextMenu(self._menu())
        self.tray.activated.connect(lambda r: self._show_me() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def _tray_icon(self) -> QIcon:
        return QIcon(logo_pixmap(64) if self.look() == "logo" else eye_pixmap(64))

    def _menu(self) -> QMenu:
        m = QMenu()
        m.addAction("Blink nu", lambda: self.blink(False))
        m.addAction("Vis påmindelsen nu", self.show_reminder)
        m.addAction("Indstillinger…", self.open_settings)
        self.act_pause = m.addAction("Pause i 1 time", lambda: self.pause(1))
        self.act_resume = m.addAction("Genoptag påmindelser", self.resume)
        self.act_resume.setVisible(False)
        m.addSeparator()
        m.addAction("Vis øjet her", self._show_me)
        m.addAction("Åbn dryeye.dk", lambda: webbrowser.open(URL_DRYEYE))
        m.addAction("Støt Red Synet", lambda: webbrowser.open(URL_REDSYNET))
        m.addSeparator()
        m.addAction("Luk Blink Buddy", QApplication.instance().quit)
        m.setStyleSheet("QMenu{background:#FBF7EC; color:#162A3B; border:1px solid #E1D6BC; padding:6px;} "
                        "QMenu::item{padding:6px 18px;} QMenu::item:selected{background:#E3ECE5;}")
        return m

    def _update_tray_pause(self):
        on = self.paused_until is not None
        for a in (getattr(self, "act_pause", None),):
            if a: a.setVisible(not on)
        if getattr(self, "act_resume", None):
            self.act_resume.setVisible(on)
        self.update()

    def _show_me(self):
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.center().x() - self.W // 2, g.center().y() - self.H // 2)
        self._save_position()
        self.show(); self.raise_()

    def _first_run_hint(self):
        if self.tray:
            self.tray.showMessage(APP_NAME, "Øjet kan flyttes med musen. Højreklik for indstillinger og pause.",
                                  QSystemTrayIcon.Information, 6000)

    def open_settings(self):
        d = SettingsDialog(self.s, None)
        d.preview_btn.clicked.connect(lambda: (self.s.setValue("remind_pos", d.pos.currentData()), self.show_reminder()))
        if d.exec() == QDialog.Accepted:
            d.save()
            self._schedule_blink()
            self._schedule_reminder()
            if self.tray:
                self.tray.setIcon(self._tray_icon())
            self.update()

    # --- mus
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.RightButton:
            self._menu().exec(QCursor.pos())

    def mouseMoveEvent(self, e):
        if self.drag_offset is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, e):
        if self.drag_offset is not None:
            self.drag_offset = None
            self._save_position()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.open_settings()

    # --- tegning
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.look() == "logo":
            paint_logo(p, QRectF(0, 6, self.W, 118), self.closed)
        else:
            eye_rect = QRectF(4, -52, self.W - 8, self.W - 8)
            paint_eye(p, eye_rect, self.closed, aura=False)
        if self.s.value("brand", "1") == "1":
            f = QFont(); f.setFamily("Segoe UI" if IS_WINDOWS else "Helvetica"); f.setPointSize(9); f.setLetterSpacing(QFont.PercentageSpacing, 104)
            p.setFont(f)
            p.setPen(QColor(74, 91, 107, 150))
            p.drawText(QRectF(0, self.H - 22, self.W, 18), Qt.AlignHCenter | Qt.AlignVCenter, "dryeye.dk")
        if self.paused_until is not None:
            p.setPen(QColor(178, 90, 60, 200))
            p.setBrush(QColor(251, 247, 236, 220))
            p.drawEllipse(QRectF(self.W - 30, 10, 18, 18))
            p.setPen(QColor(178, 90, 60, 230))
            f = QFont(); f.setPointSize(8); f.setBold(True); p.setFont(f)
            p.drawText(QRectF(self.W - 30, 10, 18, 18), Qt.AlignCenter, "II")


# ----------------------------------------------------------------------------- main
def main() -> int:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORG_NAME)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    ico = resource_path("blink_buddy.ico")
    if not os.path.exists(ico) and not IS_FROZEN:
        try:
            generate_icon(ico)
        except Exception:
            pass
    app.setWindowIcon(QIcon(ico) if os.path.exists(ico) else QIcon(eye_pixmap(64)))
    w = BlinkBuddy()
    w.show()
    test_ms = os.environ.get("BLINK_BUDDY_TEST_MS")
    if test_ms:  # til automatiserede tests: luk efter N ms
        QTimer.singleShot(int(test_ms), app.quit)
    rc = app.exec()
    w.hide()
    return rc


if __name__ == "__main__":
    sys.exit(main())
