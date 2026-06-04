from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT_DIR / "data"
STATE_PATH = STATE_DIR / "room_state.json"
CONFIG_PATH = ROOT_DIR / "config" / "client.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class AppConfig:
    rooms: list[str]
    theme: str


def load_config() -> AppConfig:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    theme = str(data.get("theme", "light"))
    if theme not in {"light", "dark"}:
        theme = "light"
    return AppConfig(
        rooms=[str(room) for room in data.get("rooms", ["1호실", "2호실", "3호실", "4호실"])],
        theme=theme,
    )


def save_theme(theme: str) -> None:
    if theme not in {"light", "dark"}:
        return

    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data["theme"] = theme
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_config_rooms(rooms: list[str]) -> None:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data["rooms"] = rooms
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class RoomState:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.rooms = self._load_or_create_rooms()

    def snapshot(self) -> dict:
        return {
            "rooms": [dict(room) for room in self.rooms],
        }

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

    def _load_or_create_rooms(self) -> list[dict]:
        if STATE_PATH.exists():
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
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

    def _save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(
                {"rooms": self.rooms},
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
