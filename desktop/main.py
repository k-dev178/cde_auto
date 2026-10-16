from __future__ import annotations

import json
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen

from PySide6.QtCore import QObject, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from desktop.state import RoomState, load_config, save_theme, save_ui_settings
from desktop.theme import GlassBackdrop, GlassPanel, glass_stylesheet


BASE_URL = "https://cde.jj.ac.kr/_custom/jj/_common/app/room-reservation/logic/ajax.jsp"
WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
PREP_ALERT_MINUTES = 30
ALERT_REPEAT_MINUTES = 5


class ReservationSignals(QObject):
    loaded = Signal(str, object, bool, bool)


class AllReservationsItem(QFrame):
    def __init__(self, on_select: Callable[[], None]) -> None:
        super().__init__()
        self.on_select = on_select
        self.setObjectName("filterItem")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self.title = QLabel("전체 예약")
        self.title.setObjectName("filterTitle")

        self.detail = QLabel("오늘 모든 CDE 예약")
        self.detail.setObjectName("filterDetail")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_select()
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        refresh_one(self)


class RoomListItem(QFrame):
    def __init__(self, room: dict, on_select: Callable[[int], None]) -> None:
        super().__init__()
        self.room = room
        self.on_select = on_select
        self.setObjectName("roomListItem")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.dot = QFrame()
        self.dot.setObjectName("statusDot")
        self.dot.setFixedSize(8, 8)

        self.name_label = QLabel()
        self.name_label.setObjectName("listRoomName")

        self.status_label = QLabel()
        self.status_label.setObjectName("listRoomStatus")

        text_stack = QVBoxLayout()
        text_stack.setContentsMargins(0, 0, 0, 0)
        text_stack.setSpacing(2)
        text_stack.addWidget(self.name_label)
        text_stack.addWidget(self.status_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(self.dot)
        layout.addLayout(text_stack, 1)

        self.update_room(room, selected=False)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_select(int(self.room["id"]))
        super().mousePressEvent(event)

    def update_room(self, room: dict, selected: bool) -> None:
        self.room = room
        occupied = bool(room["occupied"])
        self.name_label.setText(str(room["name"]))
        self.status_label.setText("사용 중" if occupied else "사용 가능")
        self.setProperty("selected", selected)
        for widget in (self, self.dot, self.status_label):
            widget.setProperty("occupied", occupied)
            widget.setProperty("selected", selected)
            refresh_one(widget)
        refresh_one(self)


class ThemeSwitch(QFrame):
    def __init__(self, on_change: Callable[[str], None]) -> None:
        super().__init__()
        self.on_change = on_change
        self.setObjectName("themeSwitch")

        self.light_button = QPushButton("화이트")
        self.light_button.setObjectName("themeOption")
        self.light_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.light_button.clicked.connect(lambda: self.on_change("light"))

        self.dark_button = QPushButton("다크")
        self.dark_button.setObjectName("themeOption")
        self.dark_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.dark_button.clicked.connect(lambda: self.on_change("dark"))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        layout.addWidget(self.light_button)
        layout.addWidget(self.dark_button)

    def set_active(self, theme: str) -> None:
        for mode, button in (("light", self.light_button), ("dark", self.dark_button)):
            button.setProperty("selected", mode == theme)
            refresh_one(button)


class ReservationRow(QFrame):
    def __init__(
        self,
        item: dict,
        checked_in: bool,
        prepared: bool,
        on_toggle_checkin: Callable[[str], None],
        on_toggle_prep: Callable[[str], None],
    ) -> None:
        super().__init__()
        self.item = item
        self.key = reservation_key(item)
        self.on_toggle_checkin = on_toggle_checkin
        self.on_toggle_prep = on_toggle_prep
        self.setObjectName("reservationRow")
        self.setProperty("checked_in", checked_in)
        self.setProperty("prepared", prepared)

        time_label = QLabel(reservation_time(item))
        time_label.setObjectName("reservationTime")

        studio_label = QLabel(str(item.get("rpName", "")))
        studio_label.setObjectName("reservationStudio")

        meta_label = QLabel(reservation_meta(item))
        meta_label.setObjectName("reservationMeta")

        purpose_label = QLabel(str(item.get("rrPurpose", "")) or "목적 없음")
        purpose_label.setObjectName("reservationPurpose")
        purpose_label.setWordWrap(True)

        state_label = QLabel(str(item.get("rrState", "")) or "상태 없음")
        state_label.setObjectName("reservationState")
        state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        state_label.setProperty("state", reservation_state_key(item))

        self.checkin_button = QPushButton("입실완료" if checked_in else "입실")
        self.checkin_button.setObjectName("reservationCheckin")
        self.checkin_button.setCheckable(True)
        self.checkin_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.checkin_button.setProperty("checked", checked_in)
        self.checkin_button.clicked.connect(lambda: self.on_toggle_checkin(self.key))

        self.prep_button = QPushButton("준비완료" if prepared else "준비")
        self.prep_button.setObjectName("reservationPrep")
        self.prep_button.setCheckable(True)
        self.prep_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.prep_button.setProperty("checked", prepared)
        self.prep_button.clicked.connect(lambda: self.on_toggle_prep(self.key))
        self.prep_button.setVisible(reservation_is_self_studio(item))

        # Keep long studio names and purposes within the glass card.
        studio_label.setWordWrap(True)
        meta_label.setWordWrap(True)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        top.addWidget(time_label)
        top.addStretch(1)
        top.addWidget(state_label)
        top.addWidget(self.prep_button)
        top.addWidget(self.checkin_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)
        layout.addLayout(top)
        layout.addWidget(studio_label)
        layout.addWidget(meta_label)
        layout.addWidget(purpose_label)

    def set_checked_in(self, checked_in: bool) -> None:
        self.checkin_button.setText("입실완료" if checked_in else "입실")
        self.checkin_button.setProperty("checked", checked_in)
        refresh_one(self.checkin_button)
        self.setProperty("checked_in", checked_in)
        refresh_one(self)

    def set_prepared(self, prepared: bool) -> None:
        self.prep_button.setText("준비완료" if prepared else "준비")
        self.prep_button.setProperty("checked", prepared)
        refresh_one(self.prep_button)
        self.setProperty("prepared", prepared)
        refresh_one(self)


class SettingsDialog(QDialog):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("설정")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setProperty("theme", parent.theme)

        title = QLabel("설정")
        title.setObjectName("settingsTitle")

        self.background_check = QCheckBox("백그라운드 실행 허용")
        self.background_check.setObjectName("settingsCheck")
        self.background_check.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.background_check.setChecked(parent.background_enabled)
        self.background_check.toggled.connect(parent.set_background_enabled)

        self.notification_scope_check = QCheckBox("셀프(1인)스튜디오만 알림")
        self.notification_scope_check.setObjectName("settingsCheck")
        self.notification_scope_check.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.notification_scope_check.setChecked(parent.notification_self_studio_only)
        self.notification_scope_check.toggled.connect(parent.set_notification_self_studio_only)

        close_button = QPushButton("닫기")
        close_button.setObjectName("refreshButton")
        close_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_button.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(self.background_check)
        layout.addWidget(self.notification_scope_check)
        layout.addWidget(close_button)


class MainWindow(QMainWindow):
    def __init__(self, state: RoomState) -> None:
        super().__init__()
        self.state = state
        self.theme = self.state.config.theme
        self.selected_room_id: int | None = None
        self.rooms_cache: list[dict] = []
        self.reservations: list[dict] = []
        self.reservation_error = False
        self.reservation_date = date.today().strftime("%Y-%m-%d")
        self.reservation_updated_at = ""
        self.reservation_checkins = self.state.checked_in_reservations(self.reservation_date)
        self.reservation_preps = self.state.prepared_reservations(self.reservation_date)
        self.reservation_rows: dict[str, ReservationRow] = {}
        self.room_items: dict[int, RoomListItem] = {}
        self.self_studio_only = self.state.config.self_studio_only
        self.sidebar_open = self.state.config.sidebar_open
        self.background_enabled = self.state.config.background_enabled
        self.notification_self_studio_only = self.state.config.notification_self_studio_only
        self.force_quit = False
        self.tray_icon: QSystemTrayIcon | None = None
        self.tray_menu: QMenu | None = None
        self.reservation_alerted_at: dict[str, datetime] = {}

        self.signals = ReservationSignals()
        self.signals.loaded.connect(self.on_reservations_loaded)

        self.setWindowTitle("CDE Studio")
        self.resize(1180, 740)
        self.setMinimumSize(980, 620)

        self.build_ui()
        self.setup_tray()
        self.apply_style()
        self.refresh()
        self.load_reservations()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.refresh_times)
        self.clock_timer.start(30000)

        self.reservation_timer = QTimer(self)
        self.reservation_timer.timeout.connect(self.load_reservations_silently)
        self.reservation_timer.start(60000)

    def setup_tray(self) -> None:
        if not self.background_enabled:
            self.teardown_tray()
            return

        if self.tray_icon is not None:
            self.update_tray_menu()
            self.tray_icon.show()
            return

        icon = app_icon(self.theme)
        self.setWindowIcon(icon)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("CDE Studio")

        self.tray_menu = QMenu(self)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.update_tray_menu()
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def update_tray_menu(self) -> None:
        if self.tray_menu is None:
            return

        self.tray_menu.clear()

        show_action = QAction("열기", self)
        show_action.triggered.connect(self.show_from_background)

        hide_action = QAction("백그라운드로 숨기기", self)
        hide_action.triggered.connect(self.hide_to_background)

        pending_items = self.pending_checkin_items(datetime.now())
        pending_action = QAction(f"준비 대기: {len(pending_items)}건", self)
        pending_action.setEnabled(False)

        self.tray_menu.addAction(show_action)
        self.tray_menu.addAction(hide_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(pending_action)

        for item, start_at, alert_type in pending_items[:5]:
            label = "미준비" if alert_type == "overdue" else "준비"
            detail = QAction(f"{label} · {start_at.strftime('%H:%M')} {item.get('rpName', '')}", self)
            detail.setEnabled(False)
            self.tray_menu.addAction(detail)

        if len(pending_items) > 5:
            more_action = QAction(f"외 {len(pending_items) - 5}건", self)
            more_action.setEnabled(False)
            self.tray_menu.addAction(more_action)

        quit_action = QAction("종료", self)
        quit_action.triggered.connect(self.quit_app)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(quit_action)

    def teardown_tray(self) -> None:
        if self.tray_icon is not None:
            self.tray_icon.hide()
            self.tray_icon.deleteLater()
            self.tray_icon = None
            self.tray_menu = None

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_from_background()

    def show_from_background(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def hide_to_background(self) -> None:
        self.hide()

    def quit_app(self) -> None:
        self.force_quit = True
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.close()
        QApplication.quit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.force_quit or not self.background_enabled or self.tray_icon is None:
            super().closeEvent(event)
            QApplication.quit()
            return

        event.ignore()
        self.hide()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def set_background_enabled(self, enabled: bool) -> None:
        self.background_enabled = enabled
        save_ui_settings(background_enabled=self.background_enabled)
        if enabled:
            self.setup_tray()
        else:
            self.teardown_tray()

    def set_notification_self_studio_only(self, enabled: bool) -> None:
        self.notification_self_studio_only = enabled
        save_ui_settings(notification_self_studio_only=self.notification_self_studio_only)
        self.update_tray_menu()
        self.notify_checkin_alerts()

    def build_ui(self) -> None:
        self.sidebar = GlassPanel()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(258)
        self.sidebar.setVisible(self.sidebar_open)
        add_shadow(self.sidebar, blur=32, offset_y=10, alpha=22)

        self.sidebar_title = QLabel("룸 목록")
        self.sidebar_title.setObjectName("sidebarTitle")

        self.sidebar_summary = QLabel()
        self.sidebar_summary.setObjectName("sidebarSummary")

        self.all_item = AllReservationsItem(self.select_all_reservations)

        self.room_list_layout = QVBoxLayout()
        self.room_list_layout.setContentsMargins(0, 0, 0, 0)
        self.room_list_layout.setSpacing(8)

        room_list_container = QWidget()
        room_list_container.setObjectName("roomListContainer")
        room_list_container.setLayout(self.room_list_layout)

        room_scroll = QScrollArea()
        room_scroll.setObjectName("roomListScroll")
        room_scroll.setWidgetResizable(True)
        room_scroll.viewport().setAutoFillBackground(False)
        room_scroll.setWidget(room_list_container)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(18, 22, 18, 18)
        sidebar_layout.setSpacing(16)
        sidebar_layout.addWidget(self.sidebar_title)
        sidebar_layout.addWidget(self.sidebar_summary)
        sidebar_layout.addWidget(self.all_item)
        sidebar_layout.addWidget(room_scroll, 1)

        self.app_label = QLabel("CDE Studio")
        self.app_label.setObjectName("appLabel")

        self.theme_switch = ThemeSwitch(self.change_theme)

        self.settings_button = QPushButton("설정")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.settings_button.clicked.connect(self.open_settings)

        self.sidebar_button = QPushButton("☰")
        self.sidebar_button.setObjectName("menuButton")
        self.sidebar_button.setToolTip("룸 목록")
        self.sidebar_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.sidebar_button.setFixedSize(38, 38)
        self.sidebar_button.setProperty("selected", self.sidebar_open)
        self.sidebar_button.clicked.connect(self.toggle_sidebar)

        self.top_bar = GlassPanel(radius=24)
        self.top_bar.setObjectName("topBar")
        add_shadow(self.top_bar, blur=24, offset_y=5, alpha=14)
        top_bar = QHBoxLayout(self.top_bar)
        top_bar.setContentsMargins(10, 8, 12, 8)
        top_bar.setSpacing(8)
        top_bar.addWidget(self.sidebar_button)
        top_bar.addWidget(self.app_label)
        top_bar.addStretch(1)
        top_bar.addWidget(self.settings_button)
        top_bar.addWidget(self.theme_switch)

        self.title = QLabel("전주대 CDE 예약 목록")
        self.title.setObjectName("title")

        self.status_summary = QLabel("예약을 불러오는 중입니다")
        self.status_summary.setObjectName("statusSummary")

        self.today = QLabel(today_label())
        self.today.setObjectName("today")

        title_stack = QVBoxLayout()
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(6)
        title_stack.addWidget(self.title)
        title_stack.addWidget(self.status_summary)
        title_stack.addWidget(self.today)

        self.reservation_surface = GlassPanel()
        self.reservation_surface.setObjectName("reservationSurface")
        add_shadow(self.reservation_surface, blur=36, offset_y=12, alpha=22)

        self.reservation_title = QLabel("오늘 예약")
        self.reservation_title.setObjectName("reservationTitle")

        self.reservation_meta = QLabel("불러오는 중")
        self.reservation_meta.setObjectName("reservationMetaHeader")

        self.prev_date_button = QPushButton("‹")
        self.prev_date_button.setObjectName("dateNavButton")
        self.prev_date_button.setToolTip("이전 날짜")
        self.prev_date_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.prev_date_button.setFixedSize(34, 34)
        self.prev_date_button.clicked.connect(lambda: self.shift_reservation_date(-1))

        self.reservation_date_label = QLabel(self.selected_reservation_label())
        self.reservation_date_label.setObjectName("reservationDateLabel")
        self.reservation_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.next_date_button = QPushButton("›")
        self.next_date_button.setObjectName("dateNavButton")
        self.next_date_button.setToolTip("다음 날짜")
        self.next_date_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.next_date_button.setFixedSize(34, 34)
        self.next_date_button.clicked.connect(lambda: self.shift_reservation_date(1))

        self.self_studio_filter = QCheckBox("셀프(1인)스튜디오만")
        self.self_studio_filter.setObjectName("selfStudioFilter")
        self.self_studio_filter.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.self_studio_filter.setChecked(self.self_studio_only)
        self.self_studio_filter.toggled.connect(self.toggle_self_studio_filter)

        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.refresh_button.clicked.connect(self.load_reservations)

        reservation_header = QHBoxLayout()
        reservation_header.setContentsMargins(24, 22, 24, 0)
        reservation_header.setSpacing(10)
        reservation_header.addWidget(self.reservation_title)
        reservation_header.addWidget(self.reservation_meta)
        reservation_header.addStretch(1)
        reservation_header.addWidget(self.refresh_button)

        date_switch = QFrame()
        date_switch.setObjectName("dateSwitch")
        date_layout = QHBoxLayout(date_switch)
        date_layout.setContentsMargins(3, 2, 3, 2)
        date_layout.setSpacing(0)
        date_layout.addWidget(self.prev_date_button)
        date_layout.addWidget(self.reservation_date_label)
        date_layout.addWidget(self.next_date_button)

        reservation_toolbar = QHBoxLayout()
        reservation_toolbar.setContentsMargins(24, 14, 24, 8)
        reservation_toolbar.setSpacing(16)
        reservation_toolbar.addWidget(date_switch)
        reservation_toolbar.addStretch(1)
        reservation_toolbar.addWidget(self.self_studio_filter)

        self.reservation_list = QVBoxLayout()
        self.reservation_list.setContentsMargins(20, 8, 20, 20)
        self.reservation_list.setSpacing(12)

        reservation_list_container = QWidget()
        reservation_list_container.setObjectName("reservationListContainer")
        reservation_list_container.setLayout(self.reservation_list)

        reservation_scroll = QScrollArea()
        reservation_scroll.setObjectName("reservationScroll")
        reservation_scroll.setWidgetResizable(True)
        reservation_scroll.viewport().setAutoFillBackground(False)
        reservation_scroll.setWidget(reservation_list_container)

        reservation_layout = QVBoxLayout(self.reservation_surface)
        reservation_layout.setContentsMargins(0, 0, 0, 0)
        reservation_layout.setSpacing(0)
        reservation_layout.addLayout(reservation_header)
        reservation_layout.addLayout(reservation_toolbar)
        reservation_layout.addWidget(reservation_scroll, 1)

        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(20)
        center_layout.addWidget(self.top_bar)
        center_layout.addLayout(title_stack)
        center_layout.addWidget(self.reservation_surface, 1)

        center = QWidget()
        center.setObjectName("centerArea")
        center.setLayout(center_layout)

        shell = QHBoxLayout()
        shell.setContentsMargins(24, 24, 24, 24)
        shell.setSpacing(24)
        shell.addWidget(self.sidebar)
        shell.addWidget(center, 1)

        self.root = GlassBackdrop()
        self.root.setObjectName("appRoot")
        self.root.setLayout(shell)
        self.setCentralWidget(self.root)

    def refresh(self) -> None:
        snapshot = self.state.snapshot()
        rooms = snapshot["rooms"]
        occupied = sum(1 for room in rooms if bool(room["occupied"]))

        self.rooms_cache = rooms
        if self.selected_room_id is not None and self.find_room_snapshot(self.selected_room_id) is None:
            self.selected_room_id = None

        self.today.setText(today_label())
        self.update_reservation_date_labels()
        self.sidebar_summary.setText(f"{len(rooms) - occupied}개 사용 가능 · {occupied}개 사용 중")
        self.render_room_list(rooms)
        self.render_reservations()

    def render_room_list(self, rooms: list[dict]) -> None:
        clear_layout(self.room_list_layout)
        self.room_items = {}
        self.all_item.set_selected(self.selected_room_id is None)

        for room in rooms:
            room_id = int(room["id"])
            item = RoomListItem(room, self.select_room)
            item.update_room(room, selected=room_id == self.selected_room_id)
            self.room_items[room_id] = item
            self.room_list_layout.addWidget(item)

        self.room_list_layout.addStretch(1)

    def render_reservations(self) -> None:
        clear_layout(self.reservation_list)
        self.reservation_rows = {}

        selected_room = self.find_room_snapshot(self.selected_room_id)
        items = self.filtered_reservations(selected_room)
        confirmed = sum(1 for item in items if item.get("rrState") == "예약완료")
        total = len(items)

        if selected_room is None:
            self.reservation_title.setText(
                "셀프(1인)스튜디오 예약" if self.self_studio_only else "예약 목록"
            )
        else:
            title = f"{selected_room['name']} 예약"
            if self.self_studio_only:
                title = f"{title} · 셀프"
            self.reservation_title.setText(title)

        if self.reservation_error:
            self.status_summary.setText("예약 데이터를 불러오지 못했습니다")
            self.reservation_meta.setText("네트워크 오류")
            self.add_reservation_empty("전주대 CDE 예약 데이터를 불러올 수 없습니다.")
            return

        if not self.reservations:
            self.status_summary.setText(f"{self.selected_reservation_label()} 예약된 내역이 없습니다")
            self.reservation_meta.setText(self.reservation_updated_at or "업데이트 대기")
            self.add_reservation_empty("선택한 날짜에 예약된 내역이 없습니다.")
            return

        if self.self_studio_only or selected_room is not None:
            self.status_summary.setText(
                f"총 {len(self.reservations)}건 중 {total}건 표시 · 예약완료 {confirmed}건"
            )
        else:
            self.status_summary.setText(
                f"총 {len(self.reservations)}건 · 예약완료 {reservation_confirmed_count(self.reservations)}건"
            )
        self.reservation_meta.setText(
            f"{total}건 표시 · 예약완료 {confirmed}건"
            if selected_room is not None
            else f"{total}건 · 예약완료 {confirmed}건"
        )

        if not items:
            if self.self_studio_only and selected_room is None:
                self.add_reservation_empty("선택한 날짜에 셀프(1인)스튜디오 예약이 없습니다.")
            elif self.self_studio_only:
                self.add_reservation_empty("선택한 룸의 셀프(1인)스튜디오 예약이 없습니다.")
            else:
                self.add_reservation_empty("선택한 룸의 선택 날짜 예약이 없습니다.")
            return

        for item in items:
            key = reservation_key(item)
            row = ReservationRow(
                item,
                key in self.reservation_checkins,
                key in self.reservation_preps,
                self.toggle_reservation_checkin,
                self.toggle_reservation_prep,
            )
            self.reservation_rows[key] = row
            self.reservation_list.addWidget(row)

        self.reservation_list.addStretch(1)

    def add_reservation_empty(self, text: str) -> None:
        empty = QLabel(text)
        empty.setObjectName("emptyState")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reservation_list.addWidget(empty)
        self.reservation_list.addStretch(1)

    def filtered_reservations(self, selected_room: dict | None) -> list[dict]:
        items = sorted(self.reservations, key=lambda item: str(item.get("rrStartTime", "")))
        if self.self_studio_only:
            items = [item for item in items if reservation_is_self_studio(item)]
        if selected_room is None:
            return items
        return [item for item in items if reservation_matches_room(item, selected_room)]

    def load_reservations(self, show_loading: bool = True) -> None:
        target_date = self.reservation_date
        if show_loading:
            self.set_reservation_loading(True)

        def worker() -> None:
            loaded_date, items, error = fetch_reservations(target_date)
            self.signals.loaded.emit(loaded_date, items, error, show_loading)

        threading.Thread(target=worker, daemon=True).start()

    def load_reservations_silently(self) -> None:
        self.load_reservations(show_loading=False)

    def on_reservations_loaded(
        self,
        target_date: str,
        items: list[dict],
        error: bool,
        show_loading: bool,
    ) -> None:
        if target_date != self.reservation_date:
            return
        self.reservation_date = target_date
        self.reservation_checkins = self.state.checked_in_reservations(self.reservation_date)
        self.reservation_preps = self.state.prepared_reservations(self.reservation_date)
        self.reservations = items
        self.reservation_error = error
        self.reservation_updated_at = datetime.now().strftime("%H:%M 업데이트")
        if show_loading:
            self.set_reservation_loading(False)
        self.update_reservation_date_labels()
        self.render_reservations()
        self.notify_checkin_alerts()
        self.update_tray_menu()

    def set_reservation_loading(self, loading: bool) -> None:
        self.refresh_button.setEnabled(not loading)
        self.prev_date_button.setEnabled(not loading)
        self.next_date_button.setEnabled(not loading)
        self.refresh_button.setText("불러오는 중" if loading else "새로고침")
        for button in (self.refresh_button, self.prev_date_button, self.next_date_button):
            refresh_one(button)

    def shift_reservation_date(self, days: int) -> None:
        selected = self.selected_reservation_date() + timedelta(days=days)
        self.reservation_date = selected.strftime("%Y-%m-%d")
        self.reservation_updated_at = ""
        self.reservations = []
        self.reservation_error = False
        self.reservation_checkins = self.state.checked_in_reservations(self.reservation_date)
        self.reservation_preps = self.state.prepared_reservations(self.reservation_date)
        self.update_reservation_date_labels()
        self.render_reservations()
        self.load_reservations()

    def selected_reservation_date(self) -> date:
        try:
            return date.fromisoformat(self.reservation_date)
        except ValueError:
            return date.today()

    def selected_reservation_label(self) -> str:
        selected = self.selected_reservation_date()
        suffix = "오늘" if selected == date.today() else WEEKDAYS[selected.weekday()]
        return selected.strftime(f"%Y.%m.%d {suffix}")

    def update_reservation_date_labels(self) -> None:
        is_today = self.selected_reservation_date() == date.today()
        self.reservation_date_label.setText(self.selected_reservation_label())
        self.all_item.detail.setText("오늘 모든 CDE 예약" if is_today else "선택 날짜 모든 CDE 예약")

    def select_all_reservations(self) -> None:
        self.selected_room_id = None
        self.refresh()

    def select_room(self, room_id: int) -> None:
        self.selected_room_id = room_id
        self.refresh()

    def toggle_sidebar(self) -> None:
        self.sidebar_open = not self.sidebar_open
        self.sidebar.setVisible(self.sidebar_open)
        self.sidebar_button.setProperty("selected", self.sidebar_open)
        save_ui_settings(sidebar_open=self.sidebar_open)
        refresh_one(self.sidebar_button)

    def toggle_reservation_checkin(self, key: str) -> None:
        if key in self.reservation_checkins:
            self.reservation_checkins.remove(key)
        else:
            self.reservation_checkins.add(key)
        self.state.save_checked_in_reservations(self.reservation_date, self.reservation_checkins)
        row = self.reservation_rows.get(key)
        if row is not None:
            row.set_checked_in(key in self.reservation_checkins)
        self.update_tray_menu()

    def toggle_reservation_prep(self, key: str) -> None:
        if key in self.reservation_preps:
            self.reservation_preps.remove(key)
        else:
            self.reservation_preps.add(key)
        self.state.save_prepared_reservations(self.reservation_date, self.reservation_preps)
        row = self.reservation_rows.get(key)
        if row is not None:
            row.set_prepared(key in self.reservation_preps)
        self.update_tray_menu()

    def pending_checkin_items(self, now: datetime) -> list[tuple[dict, datetime, str]]:
        if self.selected_reservation_date() != now.date():
            return []

        pending = []
        for item in self.reservations:
            key = reservation_key(item)
            if key in self.reservation_preps:
                continue
            if self.notification_self_studio_only and not reservation_is_self_studio(item):
                continue

            start_at = reservation_start_datetime(item, self.reservation_date)
            if start_at is None:
                continue
            if now < start_at - timedelta(minutes=PREP_ALERT_MINUTES):
                continue

            alert_type = "overdue" if now >= start_at else "prep"
            pending.append((item, start_at, alert_type))

        return sorted(pending, key=lambda value: value[1])

    def notify_checkin_alerts(self) -> None:
        if self.reservation_error or not self.reservations:
            return
        if not self.background_enabled:
            return

        if self.tray_icon is None:
            self.setup_tray()
        if self.tray_icon is None:
            return

        now = datetime.now()
        alert_items = []
        for item, start_at, alert_type in self.pending_checkin_items(now):
            key = reservation_key(item)
            alert_key = f"{self.reservation_date}|{key}|{alert_type}"
            last_alert_at = self.reservation_alerted_at.get(alert_key)
            if last_alert_at is not None and now < last_alert_at + timedelta(minutes=ALERT_REPEAT_MINUTES):
                continue

            alert_items.append((alert_key, item, start_at, alert_type))

        if not alert_items:
            return

        for alert_key, _, _, _ in alert_items:
            self.reservation_alerted_at[alert_key] = now

        first_item = alert_items[0][1]
        first_start_at = alert_items[0][2]
        has_overdue = any(alert_type == "overdue" for _, _, _, alert_type in alert_items)
        if len(alert_items) == 1:
            title = "준비 완료 확인 필요" if has_overdue else "1인 스튜디오 준비 알림"
            body = (
                "예약 시간이 되었지만 준비 완료 처리가 되지 않았습니다."
                if has_overdue
                else "예약 30분 전입니다. 1인 스튜디오 준비를 확인하세요."
            )
            message = (
                f"{first_start_at.strftime('%H:%M')} {first_item.get('rpName', '')}\n"
                f"{body}"
            )
        else:
            title = "준비 완료 확인 필요" if has_overdue else "1인 스튜디오 준비 알림"
            overdue_count = sum(1 for _, _, _, alert_type in alert_items if alert_type == "overdue")
            message = (
                f"{first_start_at.strftime('%H:%M')} {first_item.get('rpName', '')} 외 {len(alert_items) - 1}건\n"
                f"준비 미완료 {overdue_count}건, 30분 전 준비 대기 {len(alert_items) - overdue_count}건이 있습니다."
            )

        self.tray_icon.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Warning,
            10000,
        )

    def toggle_self_studio_filter(self, checked: bool) -> None:
        self.self_studio_only = checked
        save_ui_settings(self_studio_only=self.self_studio_only)
        self.render_reservations()

    def find_room_snapshot(self, room_id: int | None) -> dict | None:
        if room_id is None:
            return None
        for room in self.rooms_cache:
            if int(room["id"]) == room_id:
                return room
        return None

    def change_theme(self, theme: str) -> None:
        if theme == self.theme:
            return
        self.theme = theme
        save_theme(theme)
        self.apply_style()

    def refresh_times(self) -> None:
        self.today.setText(today_label())

    def apply_style(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setFont(QFont("Malgun Gothic", 10))

        self.root.setProperty("theme", self.theme)
        self.root.theme = self.theme
        for panel in (self.sidebar, self.reservation_surface, self.top_bar):
            panel.theme = self.theme
            panel.update()
        self.root.update()
        self.theme_switch.set_active(self.theme)

        self.setStyleSheet(glass_stylesheet(self.theme))
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            QColor("#090909" if self.theme == "dark" else "#eaf0f8"),
        )
        self.setPalette(palette)
        icon = app_icon(self.theme)
        self.setWindowIcon(icon)
        if self.tray_icon is not None:
            self.tray_icon.setIcon(icon)
        refresh_style(self.root)


def fetch_reservations(target_date: str) -> tuple[str, list[dict], bool]:
    query = urlencode({"mode": "day-list", "date": target_date})
    try:
        with urlopen(f"{BASE_URL}?{query}", timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        items = data.get("items", [])
        if not isinstance(items, list):
            items = []
        return target_date, items, False
    except Exception:
        return target_date, [], True


def clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def add_shadow(widget: QWidget, blur: int, offset_y: int, alpha: int) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, offset_y)
    shadow.setColor(QColor(29, 29, 31, alpha))
    widget.setGraphicsEffect(shadow)


def app_icon(theme: str) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    background = QColor("#f5f5f7" if theme == "dark" else "#1d1d1f")
    accent = QColor("#0a84ff" if theme == "dark" else "#0071e3")
    text = QColor("#1d1d1f" if theme == "dark" else "#ffffff")

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(background))
    painter.drawRoundedRect(QRectF(6, 6, 52, 52), 14, 14)
    painter.setBrush(QBrush(accent))
    painter.drawRoundedRect(QRectF(13, 40, 38, 7), 3.5, 3.5)
    painter.setPen(QPen(text))
    font = QFont("Arial", 20, QFont.Weight.Black)
    painter.setFont(font)
    painter.drawText(QRectF(6, 8, 52, 32), Qt.AlignmentFlag.AlignCenter, "C")
    painter.end()

    return QIcon(pixmap)


def refresh_one(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def refresh_style(widget: QWidget) -> None:
    widgets = [widget, *widget.findChildren(QWidget)]
    for item in widgets:
        refresh_one(item)


def reservation_key(item: dict) -> str:
    value = str(item.get("rrSeq", "")).strip()
    if value:
        return value
    return "|".join(
        str(item.get(key, ""))
        for key in ("rpName", "rrStartTime", "rrEndTime", "rrBooker")
    )


def reservation_time(item: dict) -> str:
    start = str(item.get("rrStartTime", ""))
    end = str(item.get("rrEndTime", ""))
    if start and end:
        return f"{start} - {end}"
    return start or end or "시간 없음"


def reservation_start_datetime(item: dict, target_date: str) -> datetime | None:
    start = str(item.get("rrStartTime", "")).strip()
    if not start:
        return None

    candidates = []
    if "T" in start or "-" in start:
        candidates.append(start)
    else:
        candidates.extend(
            [
                f"{target_date}T{start}",
                f"{target_date} {start}",
            ]
        )

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed

    for time_format in ("%H:%M", "%H:%M:%S"):
        try:
            parsed_time = datetime.strptime(start, time_format).time()
            return datetime.combine(date.fromisoformat(target_date), parsed_time)
        except ValueError:
            continue

    return None


def reservation_meta(item: dict) -> str:
    booker = str(item.get("rrBooker", "")).strip() or "예약자 없음"
    return f"예약자 · {booker}"


def reservation_state_key(item: dict) -> str:
    state = str(item.get("rrState", ""))
    if state == "예약완료":
        return "confirmed"
    if state == "취소":
        return "cancelled"
    if state == "반려":
        return "rejected"
    return "default"


def reservation_confirmed_count(items: list[dict]) -> int:
    return sum(1 for item in items if item.get("rrState") == "예약완료")


def reservation_matches_room(item: dict, room: dict) -> bool:
    studio = normalize_text(str(item.get("rpName", "")))
    room_name = normalize_text(str(room.get("name", "")))
    if room_name and (room_name in studio or studio in room_name):
        return True

    studio_digits = "".join(char for char in studio if char.isdigit())
    room_digits = "".join(char for char in room_name if char.isdigit())
    return bool(studio_digits and room_digits and studio_digits == room_digits)


def reservation_is_self_studio(item: dict) -> bool:
    studio = normalize_text(str(item.get("rpName", "")))
    if not studio:
        return False

    has_self = "셀프" in studio or "self" in studio
    one_person_tokens = ("1인", "일인", "oneperson", "single")
    return has_self and any(token in studio for token in one_person_tokens)


def normalize_text(value: str) -> str:
    return "".join(value.lower().split())


def parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def relative_time(value: str) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    seconds = max(
        0,
        int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()),
    )
    if seconds < 10:
        return "방금 전"
    if seconds < 60:
        return f"{seconds}초 전"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}분 전"

    hours = minutes // 60
    if hours < 24:
        return f"{hours}시간 전"

    return parsed.astimezone().strftime("%m.%d %H:%M")


def format_time(value: str) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def today_label() -> str:
    now = datetime.now()
    return now.strftime(f"%Y.%m.%d {WEEKDAYS[now.weekday()]}  %H:%M")


def run() -> None:
    config = load_config()
    state = RoomState(config)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(state)
    window.show()
    sys.exit(app.exec())
