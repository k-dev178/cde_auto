from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "CDEStudio"
        return Path.home() / "AppData" / "Local" / "CDEStudio"
    return Path(__file__).resolve().parents[1]


ROOT_DIR = app_root()
STATE_DIR = ROOT_DIR / "data"
STATE_PATH = STATE_DIR / "room_state.json"
CONFIG_PATH = ROOT_DIR / "config" / "client.json"
DEFAULT_ROOMS = ["1호실", "2호실", "3호실", "4호실"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class AppConfig:
    rooms: list[str]
    theme: str
    self_studio_only: bool
    sidebar_open: bool
    background_enabled: bool
    notification_self_studio_only: bool


def load_config() -> AppConfig:
    data = {}
    if CONFIG_PATH.exists():
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    theme = str(data.get("theme", "light"))
    if theme not in {"light", "dark"}:
        theme = "light"
    return AppConfig(
        rooms=[str(room) for room in data.get("rooms", DEFAULT_ROOMS)],
        theme=theme,
        self_studio_only=bool(data.get("self_studio_only", False)),
        sidebar_open=bool(data.get("sidebar_open", False)),
        background_enabled=bool(data.get("background_enabled", True)),
        notification_self_studio_only=bool(data.get("notification_self_studio_only", True)),
    )


def save_theme(theme: str) -> None:
    if theme not in {"light", "dark"}:
        return

    save_config_values(theme=theme)


def save_ui_settings(
    *,
    self_studio_only: bool | None = None,
    sidebar_open: bool | None = None,
    background_enabled: bool | None = None,
    notification_self_studio_only: bool | None = None,
) -> None:
    values = {}
    if self_studio_only is not None:
        values["self_studio_only"] = bool(self_studio_only)
    if sidebar_open is not None:
        values["sidebar_open"] = bool(sidebar_open)
    if background_enabled is not None:
        values["background_enabled"] = bool(background_enabled)
    if notification_self_studio_only is not None:
        values["notification_self_studio_only"] = bool(notification_self_studio_only)
    save_config_values(**values)


def save_config_values(**values: object) -> None:
    data = {}
    if CONFIG_PATH.exists():
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    data.update(values)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_config_rooms(rooms: list[str]) -> None:
    data = {}
    if CONFIG_PATH.exists():
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    data["rooms"] = rooms
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class RoomState:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._data = self._load_state_data()
        self.rooms = self._load_or_create_rooms(self._data)
        self.reservation_checkins = self._load_reservation_checkins(self._data)
        self.reservation_preps = self._load_reservation_preps(self._data)

    def snapshot(self) -> dict:
        return {
            "rooms": [dict(room) for room in self.rooms],
        }

    def checked_in_reservations(self, reservation_date: str) -> set[str]:
        values = self.reservation_checkins.get(reservation_date, [])
        if not isinstance(values, list):
            return set()
        return {str(value) for value in values}

    def save_checked_in_reservations(self, reservation_date: str, keys: set[str]) -> None:
        self.reservation_checkins[reservation_date] = sorted(str(key) for key in keys)
        self._save()

    def prepared_reservations(self, reservation_date: str) -> set[str]:
        values = self.reservation_preps.get(reservation_date, [])
        if not isinstance(values, list):
            return set()
        return {str(value) for value in values}

    def save_prepared_reservations(self, reservation_date: str, keys: set[str]) -> None:
        self.reservation_preps[reservation_date] = sorted(str(key) for key in keys)
        self._save()

    def toggle_room(self, room_id: int) -> dict:
        now = utc_now()
        room = self._find_room(room_id)
        room["occupied"] = not bool(room["occupied"])
        room["updated_at"] = now
        self._save()
        return dict(room)

    def add_room(self, name: str) -> dict:
        name = name.strip()
        if not name:
            name = f"{len(self.rooms) + 1}호실"

        now = utc_now()
        room = {
            "id": len(self.rooms) + 1,
            "name": name,
            "occupied": False,
            "updated_at": now,
        }
        self.rooms.append(room)
        self._save()
        self._save_config_rooms()
        return dict(room)

    def rename_room(self, room_id: int, name: str) -> dict:
        name = name.strip()
        if not name:
            raise ValueError("Room name cannot be empty")

        now = utc_now()
        room = self._find_room(room_id)
        room["name"] = name
        room["updated_at"] = now
        self._save()
        self._save_config_rooms()
        return dict(room)

    def delete_room(self, room_id: int) -> dict:
        if len(self.rooms) <= 1:
            raise ValueError("At least one room is required")

        room = dict(self._find_room(room_id))
        self.rooms = [item for item in self.rooms if int(item["id"]) != room_id]
        self._normalize_rooms()
        self._save()
        self._save_config_rooms()
        return room

    def _load_state_data(self) -> dict:
        if not STATE_PATH.exists():
            return {}
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _load_or_create_rooms(self, data: dict) -> list[dict]:
        rooms = data.get("rooms")
        if rooms:
            self._normalize_rooms(rooms)
            return rooms

        now = utc_now()
        return [
            {
                "id": index + 1,
                "name": name,
                "occupied": False,
                "updated_at": now,
            }
            for index, name in enumerate(self.config.rooms)
        ]

    def _load_reservation_checkins(self, data: dict) -> dict[str, list[str]]:
        checkins = data.get("reservation_checkins", {})
        if not isinstance(checkins, dict):
            return {}

        normalized = {}
        for reservation_date, keys in checkins.items():
            if isinstance(keys, list):
                normalized[str(reservation_date)] = [str(key) for key in keys]
        return normalized

    def _load_reservation_preps(self, data: dict) -> dict[str, list[str]]:
        preps = data.get("reservation_preps", {})
        if not isinstance(preps, dict):
            return {}

        normalized = {}
        for reservation_date, keys in preps.items():
            if isinstance(keys, list):
                normalized[str(reservation_date)] = [str(key) for key in keys]
        return normalized

    def _save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(
                {
                    "rooms": self.rooms,
                    "reservation_checkins": self.reservation_checkins,
                    "reservation_preps": self.reservation_preps,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _find_room(self, room_id: int) -> dict:
        for room in self.rooms:
            if int(room["id"]) == room_id:
                return room
        raise ValueError(f"Room not found: {room_id}")

    def _normalize_rooms(self, rooms: list[dict] | None = None) -> None:
        target = self.rooms if rooms is None else rooms
        for index, room in enumerate(target):
            room["id"] = index + 1

    def _save_config_rooms(self) -> None:
        save_config_rooms([str(room["name"]) for room in self.rooms])
