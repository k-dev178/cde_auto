from __future__ import annotations

import json
import sys
import threading
from datetime import date, datetime, timezone
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from desktop.state import RoomState, load_config, save_theme


BASE_URL = "https://cde.jj.ac.kr/_custom/jj/_common/app/room-reservation/logic/ajax.jsp"
WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


class ReservationSignals(QObject):
    loaded = Signal(str, object, bool)


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
        on_toggle_checkin: Callable[[str], None],
    ) -> None:
        super().__init__()
        self.item = item
        self.key = reservation_key(item)
        self.on_toggle_checkin = on_toggle_checkin
        self.setObjectName("reservationRow")

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
        self.checkin_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.checkin_button.setProperty("checked", checked_in)
        self.checkin_button.clicked.connect(lambda: self.on_toggle_checkin(self.key))

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        top.addWidget(time_label)
        top.addStretch(1)
        top.addWidget(state_label)
        top.addWidget(self.checkin_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addLayout(top)
        layout.addWidget(studio_label)
        layout.addWidget(meta_label)
        layout.addWidget(purpose_label)

    def set_checked_in(self, checked_in: bool) -> None:
        self.checkin_button.setText("입실완료" if checked_in else "입실")
        self.checkin_button.setProperty("checked", checked_in)
        refresh_one(self.checkin_button)


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
        self.reservation_checkins: set[str] = set()
        self.reservation_rows: dict[str, ReservationRow] = {}
        self.room_items: dict[int, RoomListItem] = {}
        self.self_studio_only = False

        self.signals = ReservationSignals()
        self.signals.loaded.connect(self.on_reservations_loaded)

        self.setWindowTitle("CDE Studio")
        self.resize(1180, 740)
        self.setMinimumSize(980, 620)

        self.build_ui()
        self.apply_style()
        self.refresh()
        self.load_reservations()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.refresh_times)
        self.clock_timer.start(30000)

        self.reservation_timer = QTimer(self)
        self.reservation_timer.timeout.connect(self.load_reservations)
        self.reservation_timer.start(30000)

    def build_ui(self) -> None:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(282)
        add_shadow(self.sidebar, blur=24, offset_y=8, alpha=12)

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
        room_scroll.setWidget(room_list_container)

        self.add_room_button = QPushButton("룸 추가")
        self.add_room_button.setObjectName("addRoomButton")
        self.add_room_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.add_room_button.clicked.connect(self.prompt_add_room)

        self.room_action_title = QLabel("선택 룸")
        self.room_action_title.setObjectName("roomActionTitle")

        self.room_action_name = QLabel("전체 예약")
        self.room_action_name.setObjectName("roomActionName")

        self.room_toggle_button = QPushButton("룸 선택")
        self.room_toggle_button.setObjectName("roomToggleButton")
        self.room_toggle_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.room_toggle_button.clicked.connect(self.toggle_selected_room)

        self.rename_button = QPushButton("이름 변경")
        self.rename_button.setObjectName("secondaryAction")
        self.rename_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.rename_button.clicked.connect(self.prompt_rename_selected_room)

        self.delete_button = QPushButton("삭제")
        self.delete_button.setObjectName("dangerAction")
        self.delete_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.delete_button.clicked.connect(self.confirm_delete_selected_room)

        room_manage = QFrame()
        room_manage.setObjectName("roomManage")
        room_manage_layout = QVBoxLayout(room_manage)
        room_manage_layout.setContentsMargins(12, 12, 12, 12)
        room_manage_layout.setSpacing(9)
        room_manage_layout.addWidget(self.room_action_title)
        room_manage_layout.addWidget(self.room_action_name)
        room_manage_layout.addWidget(self.room_toggle_button)
        room_manage_layout.addWidget(self.rename_button)
        room_manage_layout.addWidget(self.delete_button)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)
        sidebar_layout.addWidget(self.sidebar_title)
        sidebar_layout.addWidget(self.sidebar_summary)
        sidebar_layout.addWidget(self.all_item)
        sidebar_layout.addWidget(room_scroll, 1)
        sidebar_layout.addWidget(self.add_room_button)
        sidebar_layout.addWidget(room_manage)

        self.app_label = QLabel("CDE Studio")
        self.app_label.setObjectName("appLabel")

        self.local_label = QLabel("로컬")
        self.local_label.setObjectName("localLabel")
        self.local_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.theme_switch = ThemeSwitch(self.change_theme)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)
        top_bar.addWidget(self.app_label)
        top_bar.addStretch(1)
        top_bar.addWidget(self.theme_switch)
        top_bar.addWidget(self.local_label)

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

        self.reservation_surface = QFrame()
        self.reservation_surface.setObjectName("reservationSurface")
        add_shadow(self.reservation_surface, blur=28, offset_y=10, alpha=14)

        self.reservation_title = QLabel("오늘 예약")
        self.reservation_title.setObjectName("reservationTitle")

        self.reservation_meta = QLabel("불러오는 중")
        self.reservation_meta.setObjectName("reservationMetaHeader")

        self.self_studio_filter = QCheckBox("셀프(1인)스튜디오만")
        self.self_studio_filter.setObjectName("selfStudioFilter")
        self.self_studio_filter.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.self_studio_filter.toggled.connect(self.toggle_self_studio_filter)

        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.refresh_button.clicked.connect(self.load_reservations)

        reservation_header = QHBoxLayout()
        reservation_header.setContentsMargins(18, 16, 18, 6)
        reservation_header.setSpacing(10)
        reservation_header.addWidget(self.reservation_title)
        reservation_header.addWidget(self.reservation_meta)
        reservation_header.addStretch(1)
        reservation_header.addWidget(self.self_studio_filter)
        reservation_header.addWidget(self.refresh_button)

        self.reservation_list = QVBoxLayout()
        self.reservation_list.setContentsMargins(18, 8, 18, 18)
        self.reservation_list.setSpacing(10)

        reservation_list_container = QWidget()
        reservation_list_container.setObjectName("reservationListContainer")
        reservation_list_container.setLayout(self.reservation_list)

        reservation_scroll = QScrollArea()
        reservation_scroll.setObjectName("reservationScroll")
        reservation_scroll.setWidgetResizable(True)
        reservation_scroll.setWidget(reservation_list_container)

        reservation_layout = QVBoxLayout(self.reservation_surface)
        reservation_layout.setContentsMargins(0, 0, 0, 0)
        reservation_layout.setSpacing(0)
        reservation_layout.addLayout(reservation_header)
        reservation_layout.addWidget(reservation_scroll, 1)

        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(20)
        center_layout.addLayout(top_bar)
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

        self.root = QWidget()
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
        self.sidebar_summary.setText(f"{len(rooms) - occupied}개 사용 가능 · {occupied}개 사용 중")
        self.render_room_list(rooms)
        self.render_room_manage()
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

    def render_room_manage(self) -> None:
        room = self.find_room_snapshot(self.selected_room_id)
        has_room = room is not None
        if room is None:
            self.room_action_name.setText("전체 예약")
            self.room_toggle_button.setText("룸을 선택하세요")
        else:
            occupied = bool(room["occupied"])
            self.room_action_name.setText(str(room["name"]))
            self.room_toggle_button.setText("퇴실 처리" if occupied else "입실 처리")
            self.room_toggle_button.setProperty("occupied", occupied)

        for button in (self.room_toggle_button, self.rename_button, self.delete_button):
            button.setEnabled(has_room)
            refresh_one(button)

    def render_reservations(self) -> None:
        clear_layout(self.reservation_list)
        self.reservation_rows = {}

        selected_room = self.find_room_snapshot(self.selected_room_id)
        items = self.filtered_reservations(selected_room)
        confirmed = sum(1 for item in items if item.get("rrState") == "예약완료")
        total = len(items)

        if selected_room is None:
            self.reservation_title.setText(
                "셀프(1인)스튜디오 예약" if self.self_studio_only else "오늘 예약"
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
            self.status_summary.setText("오늘 예약된 내역이 없습니다")
            self.reservation_meta.setText(self.reservation_updated_at or "업데이트 대기")
            self.add_reservation_empty("오늘 예약된 내역이 없습니다.")
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
                self.add_reservation_empty("오늘 셀프(1인)스튜디오 예약이 없습니다.")
            elif self.self_studio_only:
                self.add_reservation_empty("선택한 룸의 셀프(1인)스튜디오 예약이 없습니다.")
            else:
                self.add_reservation_empty("선택한 룸의 오늘 예약이 없습니다.")
            return

        for item in items:
            key = reservation_key(item)
            row = ReservationRow(item, key in self.reservation_checkins, self.toggle_reservation_checkin)
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

    def load_reservations(self) -> None:
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("불러오는 중")

        def worker() -> None:
            target_date, items, error = fetch_today_reservations()
            self.signals.loaded.emit(target_date, items, error)

        threading.Thread(target=worker, daemon=True).start()

    def on_reservations_loaded(self, target_date: str, items: list[dict], error: bool) -> None:
        self.reservation_date = target_date
        self.reservations = items
        self.reservation_error = error
        self.reservation_updated_at = datetime.now().strftime("%H:%M 업데이트")
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("새로고침")
        self.render_reservations()

    def select_all_reservations(self) -> None:
        self.selected_room_id = None
        self.refresh()

    def select_room(self, room_id: int) -> None:
        self.selected_room_id = room_id
        self.refresh()

    def toggle_selected_room(self) -> None:
        if self.selected_room_id is None:
            return
        self.state.toggle_room(self.selected_room_id)
        self.refresh()

    def toggle_reservation_checkin(self, key: str) -> None:
        if key in self.reservation_checkins:
            self.reservation_checkins.remove(key)
        else:
            self.reservation_checkins.add(key)
        row = self.reservation_rows.get(key)
        if row is not None:
            row.set_checked_in(key in self.reservation_checkins)

    def toggle_self_studio_filter(self, checked: bool) -> None:
        self.self_studio_only = checked
        self.render_reservations()

    def prompt_add_room(self) -> None:
        default_name = f"{len(self.rooms_cache) + 1}호실"
        name, ok = QInputDialog.getText(self, "룸 추가", "룸 이름", text=default_name)
        if ok and name.strip():
            room = self.state.add_room(name)
            self.selected_room_id = int(room["id"])
            self.refresh()

    def prompt_rename_selected_room(self) -> None:
        room = self.find_room_snapshot(self.selected_room_id)
        if room is None:
            return
        name, ok = QInputDialog.getText(
            self,
            "이름 변경",
            "룸 이름",
            text=str(room["name"]),
        )
        if ok and name.strip():
            self.state.rename_room(int(room["id"]), name)
            self.refresh()

    def confirm_delete_selected_room(self) -> None:
        room = self.find_room_snapshot(self.selected_room_id)
        if room is None:
            return
        if len(self.rooms_cache) <= 1:
            QMessageBox.information(self, "삭제 불가", "룸은 최소 1개가 필요합니다.")
            return

        result = QMessageBox.question(
            self,
            "룸 삭제",
            f"{room['name']}을 삭제할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.state.delete_room(int(room["id"]))
            self.selected_room_id = None
            self.refresh()

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
        self.theme_switch.set_active(self.theme)

        self.setStyleSheet(APP_STYLE)
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            QColor("#1c1c1e" if self.theme == "dark" else "#f5f5f7"),
        )
        self.setPalette(palette)
        refresh_style(self.root)


APP_STYLE = """
QWidget#appRoot {
    background: #f5f5f7;
    color: #1d1d1f;
}
QWidget#centerArea,
QWidget#roomListContainer,
QWidget#reservationListContainer {
    background: transparent;
}
QFrame#sidebar,
QFrame#reservationSurface {
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #e5e5ea;
    border-radius: 8px;
}
QLabel#appLabel {
    color: #6e6e73;
    font-size: 13px;
    font-weight: 700;
}
QLabel#localLabel,
QFrame#themeSwitch {
    background: rgba(255, 255, 255, 0.82);
    border: 1px solid #e5e5ea;
    border-radius: 8px;
    color: #6e6e73;
}
QLabel#localLabel {
    font-size: 12px;
    font-weight: 700;
    min-width: 42px;
    padding: 6px 9px;
}
QLabel#title {
    color: #1d1d1f;
    font-size: 40px;
    font-weight: 800;
}
QLabel#statusSummary {
    color: #3a3a3c;
    font-size: 16px;
    font-weight: 700;
}
QLabel#today,
QLabel#sidebarSummary,
QLabel#reservationMetaHeader,
QLabel#reservationMeta,
QLabel#reservationPurpose {
    color: #86868b;
    font-size: 13px;
    font-weight: 500;
}
QLabel#sidebarTitle,
QLabel#reservationTitle {
    color: #1d1d1f;
    font-size: 15px;
    font-weight: 800;
}
QFrame#filterItem,
QFrame#roomListItem {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
}
QFrame#filterItem:hover,
QFrame#roomListItem:hover {
    background: #f2f2f7;
}
QFrame#filterItem[selected="true"],
QFrame#roomListItem[selected="true"] {
    background: #eaf4ff;
    border: 1px solid #cde4ff;
}
QFrame#statusDot {
    border-radius: 4px;
}
QFrame#statusDot[occupied="false"] {
    background: #34c759;
}
QFrame#statusDot[occupied="true"] {
    background: #ff9500;
}
QLabel#filterTitle,
QLabel#listRoomName,
QLabel#roomActionName,
QLabel#reservationStudio {
    color: #1d1d1f;
    font-weight: 800;
}
QLabel#filterTitle,
QLabel#listRoomName {
    font-size: 14px;
}
QLabel#filterDetail,
QLabel#listRoomStatus,
QLabel#roomActionTitle {
    color: #6e6e73;
    font-size: 12px;
    font-weight: 700;
}
QLabel#listRoomStatus[occupied="true"] {
    color: #9a4a00;
}
QFrame#roomManage {
    background: #f7f7fa;
    border: 1px solid #ececf0;
    border-radius: 8px;
}
QPushButton#addRoomButton,
QPushButton#refreshButton,
QPushButton#roomToggleButton {
    background: #0071e3;
    border: 0;
    border-radius: 8px;
    color: #ffffff;
    font-weight: 800;
}
QPushButton#addRoomButton,
QPushButton#refreshButton {
    font-size: 13px;
    padding: 9px 12px;
}
QPushButton#roomToggleButton {
    font-size: 13px;
    padding: 11px 12px;
}
QPushButton#addRoomButton:hover,
QPushButton#refreshButton:hover,
QPushButton#roomToggleButton:hover {
    background: #0077ed;
}
QPushButton#roomToggleButton[occupied="true"] {
    background: #1d1d1f;
}
QPushButton#secondaryAction,
QPushButton#dangerAction {
    border: 0;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 800;
    padding: 10px 12px;
}
QPushButton#secondaryAction {
    background: #ffffff;
    color: #1d1d1f;
}
QPushButton#secondaryAction:hover {
    background: #e5e5ea;
}
QPushButton#dangerAction {
    background: #fff0f0;
    color: #c01f2f;
}
QPushButton#dangerAction:hover {
    background: #ffe1e1;
}
QPushButton#themeOption {
    background: transparent;
    border: 0;
    border-radius: 7px;
    color: #6e6e73;
    font-size: 12px;
    font-weight: 800;
    min-width: 54px;
    padding: 6px 10px;
}
QPushButton#themeOption[selected="true"] {
    background: #ffffff;
    color: #1d1d1f;
}
QCheckBox#selfStudioFilter {
    color: #3a3a3c;
    font-size: 13px;
    font-weight: 800;
    spacing: 7px;
}
QCheckBox#selfStudioFilter::indicator {
    height: 16px;
    width: 16px;
}
QFrame#reservationRow {
    background: #ffffff;
    border: 1px solid #eeeeF2;
    border-radius: 8px;
}
QLabel#reservationTime {
    color: #0071e3;
    font-size: 18px;
    font-weight: 800;
}
QLabel#reservationStudio {
    font-size: 17px;
}
QLabel#reservationMeta {
    font-size: 13px;
}
QLabel#reservationState {
    border-radius: 8px;
    font-size: 11px;
    font-weight: 800;
    padding: 4px 9px;
}
QLabel#reservationState[state="confirmed"] {
    background: #e8f7ee;
    color: #1f7a3f;
}
QLabel#reservationState[state="cancelled"] {
    background: #fff0f0;
    color: #c01f2f;
}
QLabel#reservationState[state="rejected"] {
    background: #fff4e5;
    color: #9a4a00;
}
QLabel#reservationState[state="default"] {
    background: #f2f2f7;
    color: #6e6e73;
}
QPushButton#reservationCheckin {
    border: 0;
    border-radius: 8px;
    background: #0071e3;
    color: #ffffff;
    font-size: 12px;
    font-weight: 800;
    padding: 7px 11px;
}
QPushButton#reservationCheckin[checked="true"] {
    background: #8e8e93;
}
QLabel#emptyState {
    color: #86868b;
    font-size: 14px;
    font-weight: 600;
    padding: 40px 0;
}
QScrollArea#roomListScroll,
QScrollArea#reservationScroll {
    background: transparent;
    border: 0;
}
QScrollBar:vertical {
    background: transparent;
    margin: 0;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #c7c7cc;
    border-radius: 4px;
    min-height: 40px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QWidget#appRoot[theme="dark"] {
    background: #1c1c1e;
    color: #f5f5f7;
}
QWidget#appRoot[theme="dark"] QFrame#sidebar,
QWidget#appRoot[theme="dark"] QFrame#reservationSurface {
    background: rgba(44, 44, 46, 0.9);
    border: 1px solid #3a3a3c;
}
QWidget#appRoot[theme="dark"] QFrame#reservationRow {
    background: #2c2c2e;
    border: 1px solid #3a3a3c;
}
QWidget#appRoot[theme="dark"] QFrame#roomManage {
    background: #242426;
    border: 1px solid #3a3a3c;
}
QWidget#appRoot[theme="dark"] QLabel#title,
QWidget#appRoot[theme="dark"] QLabel#statusSummary,
QWidget#appRoot[theme="dark"] QLabel#sidebarTitle,
QWidget#appRoot[theme="dark"] QLabel#reservationTitle,
QWidget#appRoot[theme="dark"] QLabel#filterTitle,
QWidget#appRoot[theme="dark"] QLabel#listRoomName,
QWidget#appRoot[theme="dark"] QLabel#roomActionName,
QWidget#appRoot[theme="dark"] QLabel#reservationStudio {
    color: #f5f5f7;
}
QWidget#appRoot[theme="dark"] QLabel#appLabel,
QWidget#appRoot[theme="dark"] QLabel#today,
QWidget#appRoot[theme="dark"] QLabel#sidebarSummary,
QWidget#appRoot[theme="dark"] QLabel#filterDetail,
QWidget#appRoot[theme="dark"] QLabel#listRoomStatus,
QWidget#appRoot[theme="dark"] QLabel#roomActionTitle,
QWidget#appRoot[theme="dark"] QLabel#reservationMetaHeader,
QWidget#appRoot[theme="dark"] QLabel#reservationMeta,
QWidget#appRoot[theme="dark"] QLabel#reservationPurpose,
QWidget#appRoot[theme="dark"] QLabel#emptyState {
    color: #98989d;
}
QWidget#appRoot[theme="dark"] QFrame#filterItem:hover,
QWidget#appRoot[theme="dark"] QFrame#roomListItem:hover {
    background: #3a3a3c;
}
QWidget#appRoot[theme="dark"] QFrame#filterItem[selected="true"],
QWidget#appRoot[theme="dark"] QFrame#roomListItem[selected="true"] {
    background: #102f4f;
    border: 1px solid #214f79;
}
QWidget#appRoot[theme="dark"] QLabel#listRoomStatus[occupied="true"] {
    color: #ffd60a;
}
QWidget#appRoot[theme="dark"] QLabel#localLabel,
QWidget#appRoot[theme="dark"] QFrame#themeSwitch {
    background: rgba(44, 44, 46, 0.86);
    border: 1px solid #3a3a3c;
    color: #aeaeb2;
}
QWidget#appRoot[theme="dark"] QPushButton#themeOption {
    color: #aeaeb2;
}
QWidget#appRoot[theme="dark"] QPushButton#themeOption[selected="true"] {
    background: #636366;
    color: #ffffff;
}
QWidget#appRoot[theme="dark"] QCheckBox#selfStudioFilter {
    color: #f5f5f7;
}
QWidget#appRoot[theme="dark"] QPushButton#secondaryAction {
    background: #3a3a3c;
    color: #f5f5f7;
}
QWidget#appRoot[theme="dark"] QPushButton#dangerAction {
    background: #402024;
    color: #ff6961;
}
QWidget#appRoot[theme="dark"] QPushButton#roomToggleButton[occupied="true"] {
    background: #3a3a3c;
}
QWidget#appRoot[theme="dark"] QScrollBar::handle:vertical {
    background: #48484a;
}
"""


def fetch_today_reservations() -> tuple[str, list[dict], bool]:
    target_date = date.today().strftime("%Y-%m-%d")
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


def reservation_meta(item: dict) -> str:
    booker = str(item.get("rrBooker", "")).strip() or "예약자 없음"
    return f"{booker} · {str(item.get('rrPurpose', '')).strip() or '목적 없음'}"


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
    window = MainWindow(state)
    window.show()
    sys.exit(app.exec())
