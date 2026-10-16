"""Soft ambient backdrops and translucent glass surfaces for the desktop UI."""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QWidget


class GlassBackdrop(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.theme = "light"

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = self.theme == "dark"
        painter.fillRect(self.rect(), QColor("#090909" if dark else "#eaf0f8"))
        width, height = self.width(), self.height()
        # Broad, already-diffused light pools remain soft through the glass.
        pools = (
            (0.10, 0.18, 0.75, "#ffffff" if dark else "#9bbcf6", 9 if dark else 135),
            (0.86, 0.22, 0.65, "#ffffff" if dark else "#dbc4f1", 5 if dark else 140),
            (0.62, 0.94, 0.72, "#ffffff" if dark else "#9edddc", 3 if dark else 125),
            (0.92, 0.90, 0.43, "#ffffff" if dark else "#f3d8cf", 2 if dark else 135),
        )
        for x, y, radius, color, alpha in pools:
            gradient = QRadialGradient(QPointF(width * x, height * y), max(width, height) * radius)
            tint = QColor(color)
            tint.setAlpha(alpha)
            gradient.setColorAt(0, tint)
            tint.setAlpha(0)
            gradient.setColorAt(1, tint)
            painter.fillRect(self.rect(), gradient)


class GlassPanel(QFrame):
    def __init__(self, radius: int = 26) -> None:
        super().__init__()
        self.radius = radius
        self.theme = "light"

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = self.theme == "dark"
        rect = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
        fill.setColorAt(0, QColor(255, 255, 255, 16 if dark else 165))
        fill.setColorAt(0.48, QColor(22, 22, 22, 100) if dark else QColor(255, 255, 255, 85))
        fill.setColorAt(1, QColor(255, 255, 255, 6) if dark else QColor(255, 255, 255, 125))
        painter.fillPath(path, fill)
        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim.setColorAt(0, QColor(255, 255, 255, 55 if dark else 245))
        rim.setColorAt(0.45, QColor(255, 255, 255, 14 if dark else 80))
        rim.setColorAt(1, QColor(255, 255, 255, 25 if dark else 185))
        painter.setPen(QPen(rim, 1.2))
        painter.drawPath(path)
        inner = rect.adjusted(1.5, 1.5, -1.5, -1.5)
        painter.setPen(QPen(QColor(255, 255, 255, 12 if dark else 70), 0.7))
        painter.drawRoundedRect(inner, self.radius - 1.5, self.radius - 1.5)


def glass_stylesheet(theme: str) -> str:
    dark = theme == "dark"
    colors = {
        "checkmark": (Path(__file__).resolve().parents[1] / "assets" / "checkmark.svg").as_posix(),
        "text": "#f2f2f2" if dark else "#24344c",
        "muted": "#b5b5b5" if dark else "#566981",
        "faint": "#999999" if dark else "#62748b",
        "accent": "#eeeeee" if dark else "#1764b5",
        "control": "rgba(255,255,255,10)" if dark else "rgba(255,255,255,125)",
        "hover": "rgba(255,255,255,22)" if dark else "rgba(255,255,255,205)",
        "edge": "rgba(255,255,255,28)" if dark else "rgba(255,255,255,220)",
        "selected": "rgba(255,255,255,18)" if dark else "rgba(225,241,255,185)",
        "selected_edge": "rgba(255,255,255,58)" if dark else "rgba(122,179,238,145)",
        "row": "rgba(255,255,255,5)" if dark else "rgba(255,255,255,115)",
        "row_edge": "rgba(255,255,255,20)" if dark else "rgba(255,255,255,215)",
        "green": "#89e2bb" if dark else "#176c50",
        "green_bg": "rgba(61,186,138,16)" if dark else "rgba(218,249,233,165)",
        "amber": "#f4cc85" if dark else "#85531c",
        "amber_bg": "rgba(232,174,71,14)" if dark else "rgba(255,242,215,185)",
        "red": "#ffb3bd" if dark else "#b13a52",
        "red_bg": "rgba(223,97,125,30)" if dark else "rgba(255,228,233,185)",
        "dialog": "#181818" if dark else "#edf3fb",
        "disabled": "#666666" if dark else "#8898ad",
        "primary_top": "#424242" if dark else "#5a9df1",
        "primary_mid": "#2e2e2e" if dark else "#367ed9",
        "primary_bottom": "#252525" if dark else "#266ac4",
        "primary_hover_top": "#505050" if dark else "#75b1fc",
        "primary_hover_bottom": "#333333" if dark else "#347bd4",
        "check": "#808080" if dark else "#448be0",
        "check_edge": "#b0b0b0" if dark else "#8dbcf4",
        "check_hover": "#999999" if dark else "#64a4f0",
    }
    return """
QWidget { color: %(text)s; font-family: "Malgun Gothic"; font-size: 13px; }
QLabel, QWidget#centerArea, QWidget#roomListContainer, QWidget#reservationListContainer {
    background: transparent;
}
QFrame#sidebar, QFrame#reservationSurface, QFrame#topBar { background: transparent; border: none; }
QLabel#appLabel { font-size: 15px; font-weight: 700; }
QLabel#title { font-size: 34px; font-weight: 800; letter-spacing: -1px; }
QLabel#statusSummary { color: %(muted)s; font-size: 15px; font-weight: 500; }
QLabel#today, QLabel#sidebarSummary, QLabel#reservationMetaHeader,
QLabel#reservationMeta, QLabel#reservationPurpose { color: %(faint)s; font-size: 12px; }
QLabel#sidebarTitle, QLabel#reservationTitle { font-size: 16px; font-weight: 700; }
QFrame#themeSwitch, QFrame#dateSwitch {
    background: %(control)s; border: 1px solid %(edge)s; border-radius: 18px;
}
QPushButton { background: %(control)s; border: 1px solid %(edge)s; border-radius: 16px;
    padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: %(hover)s; border-color: %(selected_edge)s; }
QPushButton:pressed { background: %(selected)s; border-color: %(accent)s; }
QPushButton:focus { border-color: %(accent)s; }
QPushButton:disabled { color: %(disabled)s; background: %(control)s; border-color: %(row_edge)s; }
QPushButton#menuButton { padding: 0; border-radius: 18px; font-size: 18px; }
QPushButton#menuButton[selected="true"] { background: %(selected)s; border-color: %(selected_edge)s; color: %(accent)s; }
QPushButton#themeOption { background: transparent; border: 1px solid transparent;
    border-radius: 14px; color: %(muted)s; min-width: 42px; min-height: 18px; padding: 5px 10px; font-size: 11px; }
QPushButton#themeOption[selected="true"] { background: %(hover)s; border-color: %(edge)s; color: %(text)s; }
QFrame#filterItem, QFrame#roomListItem { background: transparent; border: 1px solid transparent; border-radius: 17px; }
QFrame#filterItem:hover, QFrame#roomListItem:hover { background: %(control)s; border-color: %(edge)s; }
QFrame#filterItem[selected="true"], QFrame#roomListItem[selected="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 %(hover)s,stop:1 %(selected)s);
    border: 1px solid %(selected_edge)s;
}
QLabel#filterTitle, QLabel#listRoomName { font-size: 14px; font-weight: 700; }
QLabel#filterDetail, QLabel#listRoomStatus { color: %(muted)s; font-size: 11px; }
QLabel#listRoomStatus[occupied="true"] { color: %(amber)s; }
QFrame#statusDot { background: #41bd91; border: 1px solid rgba(255,255,255,100); border-radius: 4px; }
QFrame#statusDot[occupied="true"] { background: #edb66c; }
QPushButton#refreshButton, QPushButton#reservationCheckin {
    color: white; border: 1px solid rgba(255,255,255,100);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %(primary_top)s,stop:0.48 %(primary_mid)s,stop:1 %(primary_bottom)s);
}
QPushButton#refreshButton:hover, QPushButton#reservationCheckin:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %(primary_hover_top)s,stop:1 %(primary_hover_bottom)s);
}
QPushButton#refreshButton:disabled { background: %(control)s; color: %(disabled)s; }
QLabel#reservationDateLabel { min-width: 142px; font-size: 12px; font-weight: 600; }
QPushButton#dateNavButton { background: transparent; border-color: transparent; padding: 0; border-radius: 14px; font-size: 18px; }
QPushButton#dateNavButton:hover { background: %(hover)s; }
QCheckBox { spacing: 8px; color: %(muted)s; font-size: 12px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid %(selected_edge)s;
    border-radius: 4px; background: %(control)s; }
QCheckBox::indicator:unchecked:hover { background: %(hover)s; border-color: %(check_edge)s; }
QCheckBox::indicator:checked { background: %(check)s; border: 1px solid %(check_edge)s;
    image: url("%(checkmark)s"); }
QCheckBox::indicator:checked:hover { background: %(check_hover)s; }
QCheckBox:focus { color: %(accent)s; }
QFrame#reservationRow { background: %(row)s; border: 1px solid %(row_edge)s; border-radius: 20px; }
QFrame#reservationRow:hover { background: %(control)s; border-color: %(selected_edge)s; }
QFrame#reservationRow[prepared="true"] { background: %(amber_bg)s; border-color: rgba(229,177,96,145); }
QFrame#reservationRow[checked_in="true"] { background: %(green_bg)s; border-color: rgba(92,188,149,145); }
QFrame#reservationRow[prepared="true"][checked_in="true"] { border: 2px solid rgba(92,188,149,185); }
QLabel#reservationTime { color: %(accent)s; font-size: 20px; font-weight: 700; }
QLabel#reservationStudio { font-size: 16px; font-weight: 700; }
QLabel#reservationState { background: %(control)s; color: %(muted)s; border: 1px solid %(edge)s;
    border-radius: 11px; min-height: 14px; padding: 4px 10px; font-size: 11px; font-weight: 600; }
QLabel#reservationState[state="confirmed"] { background: %(green_bg)s; color: %(green)s; }
QLabel#reservationState[state="cancelled"] { background: %(red_bg)s; color: %(red)s; }
QLabel#reservationState[state="rejected"] { background: %(amber_bg)s; color: %(amber)s; }
QPushButton#reservationCheckin, QPushButton#reservationPrep { min-width: 54px; min-height: 18px; padding: 6px 12px; border-radius: 14px; font-size: 11px; }
QPushButton#reservationPrep { background: %(amber_bg)s; color: %(amber)s; border-color: rgba(229,177,96,130); }
QPushButton#reservationCheckin[checked="true"], QPushButton#reservationPrep[checked="true"] {
    background: %(green_bg)s; color: %(green)s; border-color: rgba(92,188,149,145);
}
QLabel#emptyState { color: %(muted)s; font-size: 14px; padding: 60px 16px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; margin: 4px 0; width: 6px; }
QScrollBar::handle:vertical { background: %(selected_edge)s; border-radius: 3px; min-height: 40px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QDialog, QMenu { background: %(dialog)s; }
QLabel#settingsTitle { font-size: 21px; font-weight: 700; }
QCheckBox#settingsCheck { font-size: 13px; }
QLineEdit { background: %(control)s; border: 1px solid %(edge)s; border-radius: 10px; padding: 8px; }
QMenu { border: 1px solid %(edge)s; padding: 6px; }
QMenu::item { padding: 8px 16px; border-radius: 6px; }
QMenu::item:selected { background: %(selected)s; }
""" % colors
