import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from threading import Thread
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop import main, state


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.config_path = root / "config" / "client.json"
        self.state_path = root / "data" / "room_state.json"
        for name, value in (("CONFIG_PATH", self.config_path), ("STATE_PATH", self.state_path)):
            patcher = patch.object(state, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_config(self, content):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(content, encoding="utf-8")

    def test_corrupt_config_recovers_without_losing_original(self):
        content = '{"theme":'
        self.write_config(content)
        self.assertEqual(state.load_config().rooms, state.DEFAULT_ROOMS)
        state.save_theme("dark")
        self.assertEqual(json.loads(self.config_path.read_text(encoding="utf-8"))["theme"], "dark")
        backups = list(self.config_path.parent.glob("client.json.corrupt-*"))
        self.assertTrue(backups)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), content)

    def test_invalid_config_fields_use_defaults(self):
        self.write_config(json.dumps({"rooms": None, "background_enabled": "false"}))
        config = state.load_config()
        self.assertEqual(config.rooms, state.DEFAULT_ROOMS)
        self.assertFalse(config.background_enabled)

    def test_config_accepts_utf8_bom(self):
        self.write_config('\ufeff{"theme":"dark"}')
        self.assertEqual(state.load_config().theme, "dark")

    def test_invalid_saved_rooms_do_not_break_startup(self):
        self.state_path.parent.mkdir(parents=True)
        self.state_path.write_text(json.dumps({"rooms": [None, {"name": "1호실"}]}), encoding="utf-8")
        rooms = state.RoomState(state.load_config()).snapshot()["rooms"]
        self.assertEqual(rooms[0]["name"], "1호실")
        self.assertFalse(rooms[0]["occupied"])

    def test_truncated_state_recovers(self):
        self.state_path.parent.mkdir(parents=True)
        self.state_path.write_text('{"rooms":', encoding="utf-8")
        rooms = state.RoomState(state.load_config()).snapshot()["rooms"]
        self.assertEqual(len(rooms), 4)

    def test_failed_atomic_save_preserves_previous_checkins(self):
        room_state = state.RoomState(state.load_config())
        room_state.save_checked_in_reservations("2026-10-16", {"original"})
        original = self.state_path.read_bytes()
        with patch.object(state.os, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                room_state.save_checked_in_reservations("2026-10-16", {"new"})
        self.assertEqual(self.state_path.read_bytes(), original)
        self.assertEqual(list(self.state_path.parent.glob("*.tmp")), [])

    def test_saved_checkins_and_preparations_survive_restart(self):
        room_state = state.RoomState(state.load_config())
        room_state.save_checked_in_reservations("2026-10-16", {"checked"})
        room_state.save_prepared_reservations("2026-10-16", {"prepared"})
        restored = state.RoomState(state.load_config())
        self.assertEqual(restored.checked_in_reservations("2026-10-16"), {"checked"})
        self.assertEqual(restored.prepared_reservations("2026-10-16"), {"prepared"})

    def test_saving_settings_retains_other_preferences(self):
        self.write_config(json.dumps({"theme": "dark", "rooms": ["회의실"], "sidebar_open": True}))
        state.save_ui_settings(self_studio_only=True)
        restored = state.load_config()
        self.assertEqual(restored.theme, "dark")
        self.assertEqual(restored.rooms, ["회의실"])
        self.assertTrue(restored.sidebar_open)
        self.assertTrue(restored.self_studio_only)


class ReservationTests(unittest.TestCase):
    def test_room_numbers_do_not_match_by_suffix(self):
        self.assertFalse(main.reservation_matches_room({"rpName": "11호실"}, {"name": "1호실"}))
        self.assertTrue(main.reservation_matches_room({"rpName": "셀프(1인)스튜디오 1호실"}, {"name": "1호실"}))

    def test_missing_room_name_does_not_match_every_room(self):
        self.assertFalse(main.reservation_matches_room({"rpName": ""}, {"name": "1호실"}))

    def test_eleven_person_studio_is_not_single_person(self):
        self.assertFalse(main.reservation_is_self_studio({"rpName": "셀프(11인)스튜디오"}))
        self.assertTrue(main.reservation_is_self_studio({"rpName": "셀프(1인)스튜디오"}))

    def test_null_reservation_ids_use_distinct_fallback_keys(self):
        first = {"rrSeq": None, "rpName": "1호실", "rrStartTime": "10:00"}
        second = {"rrSeq": None, "rpName": "2호실", "rrStartTime": "10:00"}
        self.assertNotEqual(main.reservation_key(first), main.reservation_key(second))

    def test_malformed_server_response_is_an_error(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        for payload in ({"items": [None]}, {"items": "invalid"}, {"error": "unavailable"}):
            response.read.return_value = json.dumps(payload).encode()
            with self.subTest(payload=payload), patch.object(main, "urlopen", return_value=response):
                self.assertTrue(main.fetch_reservations("2026-10-16")[2])

    def test_empty_and_populated_server_responses_are_accepted(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        for items in ([], [{"rrSeq": 1, "rrState": "예약완료"}]):
            response.read.return_value = json.dumps({"items": items}).encode()
            with self.subTest(items=items), patch.object(main, "urlopen", return_value=response):
                self.assertEqual(main.fetch_reservations("2026-10-16"), ("2026-10-16", items, False))


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        class Today(date):
            @classmethod
            def today(cls):
                return cls(2026, 10, 16)
        date_patcher = patch.object(main, "date", Today)
        date_patcher.start()
        self.addCleanup(date_patcher.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        for name, value in (("CONFIG_PATH", root / "client.json"), ("STATE_PATH", root / "room_state.json")):
            patcher = patch.object(state, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        thread_patcher = patch.object(main.threading, "Thread")
        self.thread_class = thread_patcher.start()
        self.addCleanup(thread_patcher.stop)
        config = state.AppConfig(state.DEFAULT_ROOMS[:], "light", False, True, False, False)
        self.window = main.MainWindow(state.RoomState(config))
        self.window.clock_timer.stop()
        self.window.reservation_timer.stop()
        self.window.reservation_date = "2026-10-16"
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.force_quit = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def reservation(self, **values):
        item = {"rrSeq": "1", "rpName": "셀프(1인)스튜디오 1호실", "rrState": "예약완료", "rrStartTime": "10:00", "rrEndTime": "11:00"}
        item.update(values)
        return item

    def test_cancelled_checked_in_prepared_and_finished_reservations_do_not_alert(self):
        now = datetime(2026, 10, 16, 10, 30)
        for item, checked_in, prepared in (
            (self.reservation(rrState="취소"), set(), set()),
            (self.reservation(rrState="반려"), set(), set()),
            (self.reservation(), {"1"}, set()),
            (self.reservation(), set(), {"1"}),
            (self.reservation(rrEndTime="10:15"), set(), set()),
        ):
            with self.subTest(item=item, checked_in=checked_in, prepared=prepared):
                self.window.reservations = [item]
                self.window.reservation_checkins = checked_in
                self.window.reservation_preps = prepared
                self.assertEqual(self.window.pending_checkin_items(now), [])

    def test_active_and_upcoming_reservations_still_alert(self):
        self.window.reservations = [self.reservation()]
        for now, kind in ((datetime(2026, 10, 16, 9, 30), "prep"), (datetime(2026, 10, 16, 10, 30), "overdue")):
            with self.subTest(now=now):
                self.assertEqual(self.window.pending_checkin_items(now)[0][2], kind)
        self.assertEqual(self.window.pending_checkin_items(datetime(2026, 10, 16, 9, 29)), [])

    def test_checkin_buttons_reflect_restored_state(self):
        row = main.ReservationRow(self.reservation(), True, True, Mock(), Mock())
        self.addCleanup(row.deleteLater)
        self.assertTrue(row.checkin_button.isChecked())
        self.assertTrue(row.prep_button.isChecked())
        row.set_checked_in(False)
        row.set_prepared(False)
        self.assertFalse(row.checkin_button.isChecked())
        self.assertFalse(row.prep_button.isChecked())

    def test_refresh_click_shows_loading_and_deduplicates_timer_requests(self):
        # Complete the initial request before clicking Refresh.
        self.window.signals.loaded.emit(1, self.window.reservation_date, [], False)
        self.window.refresh_button.click()
        self.assertFalse(self.window.refresh_button.isEnabled())
        calls = self.thread_class.call_count
        self.window.load_reservations_silently()
        self.assertEqual(self.thread_class.call_count, calls)

    def test_worker_result_updates_rows_and_releases_loading(self):
        worker = self.thread_class.call_args.kwargs["target"]
        items = [self.reservation()]
        with patch.object(main, "fetch_reservations", return_value=("2026-10-16", items, False)):
            worker()
        self.assertEqual(self.window.reservations, items)
        self.assertEqual(set(self.window.reservation_rows), {"1"})
        self.assertTrue(self.window.refresh_button.isEnabled())
        self.assertFalse(self.window._reservation_request_pending)

    def test_background_worker_delivers_result_to_gui(self):
        worker = self.thread_class.call_args.kwargs["target"]
        items = [self.reservation()]
        with patch.object(main, "fetch_reservations", return_value=("2026-10-16", items, False)):
            thread = Thread(target=worker)
            thread.start()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.app.processEvents()
        self.assertEqual(self.window.reservations, items)
        self.assertTrue(self.window.refresh_button.isEnabled())

    def test_stale_response_cannot_replace_newer_date_request(self):
        self.window.shift_reservation_date(1)
        self.window.shift_reservation_date(-1)
        old = [self.reservation(rrSeq="old")]
        latest = [self.reservation(rrSeq="new")]
        self.window.signals.loaded.emit(3, "2026-10-16", latest, False)
        self.window.signals.loaded.emit(1, "2026-10-16", old, False)
        self.assertEqual(self.window.reservations, latest)
        self.assertTrue(self.window.refresh_button.isEnabled())

    def test_midnight_follows_today_and_retains_explicit_other_date(self):
        class Tomorrow(date):
            @classmethod
            def today(cls):
                return cls(2026, 10, 17)
        self.window._last_today = date(2026, 10, 16)
        with patch.object(main, "date", Tomorrow):
            self.window.refresh_times()
        self.assertEqual(self.window.reservation_date, "2026-10-17")
        self.window._last_today = date(2026, 10, 16)
        self.window.reservation_date = "2026-10-12"
        with patch.object(main, "date", Tomorrow):
            self.window.refresh_times()
        self.assertEqual(self.window.reservation_date, "2026-10-12")

    def test_rebuilding_tray_menu_does_not_accumulate_actions(self):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu
        self.window.tray_menu = QMenu(self.window)
        self.window.update_tray_menu()
        count = len(self.window.findChildren(QAction))
        for _ in range(10):
            self.window.update_tray_menu()
        self.assertEqual(len(self.window.findChildren(QAction)), count)


if __name__ == "__main__":
    unittest.main()
