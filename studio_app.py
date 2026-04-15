#!/usr/bin/env python3
"""
CDE 스튜디오 대여 현황 데스크탑 앱 - 오늘 예약 조회
macOS / Windows 공통 (Python 3.8+, 외부 라이브러리 불필요)
"""

import sys
import tkinter as tk
from tkinter import ttk
import requests
import subprocess
from datetime import date, datetime, timedelta
import threading

BASE_URL = "https://cde.jj.ac.kr/_custom/jj/_common/app/room-reservation/logic/ajax.jsp"

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# OS별 폰트
FONT = "AppleGothic" if IS_MAC else "맑은 고딕"

STATE_STYLE = {
    "예약완료": ("#16a34a", "#ffffff", "#f0fdf4"),
    "예약대기": ("#64748b", "#ffffff", "#f8fafc"),
    "취소":     ("#dc2626", "#ffffff", "#fff1f2"),
    "반려":     ("#ea580c", "#ffffff", "#fff7ed"),
}
DEFAULT_STYLE = ("#64748b", "#ffffff", "#f8fafc")
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

COLUMNS = [
    ("스튜디오", True,  160, "w"),
    ("시간",     False, 155, "center"),
    ("예약자",   False, 75,  "center"),
    ("목적",     True,  140, "w"),
    ("상태",     False, 90,  "center"),
    ("입실",     False, 88,  "center"),
]
NCOLS = len(COLUMNS)


# ── 알림 (OS별) ───────────────────────────────────────────────────────────────

def notify(title: str, body: str):
    if IS_MAC:
        # macOS: osascript (소리 없음)
        safe_title = title.replace('"', '')
        safe_body  = body.replace('"', '').replace('\n', ' ')
        subprocess.Popen(
            ["osascript", "-e", f'display notification "{safe_body}" with title "{safe_title}"'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    elif IS_WIN:
        # Windows: PowerShell 풍선 알림 (별도 창 없이)
        safe_title = title.replace("'", "").replace('"', '')
        safe_body  = body.replace("'", "").replace('"', '').replace('\n', ' ')
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$n=New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon=[System.Drawing.SystemIcons]::Information;"
            "$n.Visible=$true;"
            f"$n.ShowBalloonTip(6000,'{safe_title}','{safe_body}',"
            "[System.Windows.Forms.ToolTipIcon]::None);"
            "Start-Sleep 7;$n.Dispose()"
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WIN else 0
        )


# ── API ───────────────────────────────────────────────────────────────────────

def fetch_today():
    today = date.today().strftime("%Y-%m-%d")
    try:
        r = requests.get(BASE_URL, params={"mode": "day-list", "date": today}, timeout=10)
        return today, r.json().get("items", [])
    except Exception:
        return today, None


# ── 앱 ───────────────────────────────────────────────────────────────────────

class StudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CDE 스튜디오 대여 현황")
        self.root.configure(bg="#f1f5f9")
        self.root.geometry("920x460")
        self.root.minsize(700, 300)

        self.items:       list = []
        self.checkin_set: set  = set()
        self.alerted_set: set  = set()
        self._btn_refs:   dict = {}

        self._build_ui()
        self._load()
        self.root.after(30_000, self._timer_tick)

    def _f(self, size, bold=False):
        """OS별 폰트 튜플 반환"""
        return (FONT, size, "bold") if bold else (FONT, size)

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        hdr = tk.Frame(self.root, bg="#1e3a8a")
        hdr.pack(fill="x")

        self.date_label = tk.Label(hdr, text="", font=self._f(15, True),
                                   bg="#1e3a8a", fg="#ffffff", pady=13)
        self.date_label.pack(side="left", padx=22)

        self.count_label = tk.Label(hdr, text="", font=self._f(11),
                                    bg="#1e3a8a", fg="#93c5fd")
        self.count_label.pack(side="left")

        self.status_var = tk.StringVar(value="")
        tk.Label(hdr, textvariable=self.status_var, font=self._f(10),
                 bg="#1e3a8a", fg="#60a5fa").pack(side="right", padx=22)

        tk.Frame(self.root, bg="#1e40af", height=2).pack(fill="x")

        outer = tk.Frame(self.root, bg="#ffffff")
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(outer, bg="#ffffff", highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.table = tk.Frame(self.canvas, bg="#ffffff")
        self._fid = self.canvas.create_window((0, 0), window=self.table, anchor="nw")
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._fid, width=e.width))
        self.table.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        for col, (_, stretch, minw, _) in enumerate(COLUMNS):
            self.table.columnconfigure(col, weight=1 if stretch else 0, minsize=minw)

        # 헤더 행 (row=0)
        for col, (title, _, _, anchor) in enumerate(COLUMNS):
            tk.Label(self.table, text=title, font=self._f(10, True),
                     bg="#f1f5f9", fg="#64748b",
                     anchor=anchor, padx=12, pady=8
                     ).grid(row=0, column=col, sticky="ew")
        tk.Frame(self.table, bg="#e2e8f0", height=1
                 ).grid(row=1, column=0, columnspan=NCOLS, sticky="ew")

        bottom = tk.Frame(self.root, bg="#f1f5f9")
        bottom.pack(fill="x")
        btn = tk.Label(bottom, text="  새로고침  ", font=self._f(11, True),
                       bg="#1e40af", fg="white", cursor="hand2", pady=7, padx=4)
        btn.pack(side="right", padx=18, pady=9)
        btn.bind("<Button-1>", lambda e: self._on_refresh())
        btn.bind("<Enter>",    lambda e: btn.config(bg="#1d4ed8"))
        btn.bind("<Leave>",    lambda e: btn.config(bg="#1e40af"))

    # ── 데이터 로드 ──────────────────────────────────────────────────────────

    def _load(self):
        self.status_var.set("불러오는 중…")
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        today, items = fetch_today()
        self.root.after(0, self._render, today, items)

    def _on_refresh(self):
        self._load()

    # ── 렌더링 ───────────────────────────────────────────────────────────────

    def _render(self, today_str, items):
        dt = date.today()
        self.date_label.config(
            text=f"{dt.year}년 {dt.month}월 {dt.day}일 ({WEEKDAY_KO[dt.weekday()]})")
        self.status_var.set(datetime.now().strftime("%H:%M 업데이트"))

        if items is not None:
            self.items = items

        for w in self.table.winfo_children():
            info = w.grid_info()
            if info and int(info.get("row", 0)) >= 2:
                w.destroy()
        self._btn_refs.clear()

        if items is None:
            self.count_label.config(text="  네트워크 오류", fg="#fca5a5")
            self._empty_row("데이터를 불러올 수 없습니다.")
            return

        total     = len(items)
        confirmed = sum(1 for i in items if i.get("rrState") == "예약완료")
        self.count_label.config(
            fg="#93c5fd",
            text=f"  총 {total}건  (예약완료 {confirmed}건)" if total else "")

        if not total:
            self._empty_row("오늘 예약된 내역이 없습니다.")
            return

        for idx, item in enumerate(sorted(items, key=lambda x: x.get("rrStartTime", ""))):
            state  = item.get("rrState", "")
            rr_seq = item.get("rrSeq", "")
            badge_bg, badge_fg, row_bg = STATE_STYLE.get(state, DEFAULT_STYLE)
            grid_row = 2 + idx * 2
            sep_row  = grid_row + 1

            values = [
                item.get("rpName", ""),
                f"{item.get('rrStartTime','')} ~ {item.get('rrEndTime','')}",
                item.get("rrBooker", ""),
                item.get("rrPurpose", ""),
            ]
            for col, (text, (_, _, _, anchor)) in enumerate(zip(values, COLUMNS)):
                tk.Label(self.table, text=text, font=self._f(12),
                         bg=row_bg, fg="#1e293b",
                         anchor=anchor, padx=12, pady=11
                         ).grid(row=grid_row, column=col, sticky="ew")

            # 상태 뱃지
            cell4 = tk.Frame(self.table, bg=row_bg)
            cell4.grid(row=grid_row, column=4, sticky="ew")
            tk.Label(cell4, text=state, font=self._f(10, True),
                     bg=badge_bg, fg=badge_fg, padx=10, pady=3
                     ).pack(expand=True)

            # 입실 버튼
            already_in = rr_seq in self.checkin_set
            cell5 = tk.Frame(self.table, bg=row_bg)
            cell5.grid(row=grid_row, column=5, sticky="ew")
            btn = tk.Label(cell5,
                           text="입실완료" if already_in else "입실",
                           font=self._f(10, True),
                           bg="#94a3b8" if already_in else "#2563eb",
                           fg="white", padx=10, pady=3,
                           cursor="hand2")
            btn.pack(expand=True, pady=6)
            if already_in:
                btn.bind("<Button-1>", lambda e, i=item, b=btn: self._on_cancel_checkin(i, b))
                btn.bind("<Enter>",    lambda e, b=btn: b.config(bg="#64748b"))
                btn.bind("<Leave>",    lambda e, b=btn: b.config(bg="#94a3b8"))
            else:
                btn.bind("<Button-1>", lambda e, i=item, b=btn: self._on_checkin(i, b))
                btn.bind("<Enter>",    lambda e, b=btn: b.config(bg="#1d4ed8"))
                btn.bind("<Leave>",    lambda e, b=btn: b.config(bg="#2563eb"))

            self._btn_refs[rr_seq] = btn

            tk.Frame(self.table, bg="#e2e8f0", height=1
                     ).grid(row=sep_row, column=0, columnspan=NCOLS, sticky="ew")

    def _empty_row(self, msg):
        tk.Label(self.table, text=msg, font=self._f(12),
                 bg="#ffffff", fg="#94a3b8", pady=50
                 ).grid(row=2, column=0, columnspan=NCOLS, sticky="ew")

    # ── 입실 ─────────────────────────────────────────────────────────────────

    def _on_checkin(self, item, btn):
        rr_seq = item.get("rrSeq", "")
        self.checkin_set.add(rr_seq)
        btn.config(text="입실완료", bg="#94a3b8", cursor="hand2")
        btn.bind("<Button-1>", lambda e, i=item, b=btn: self._on_cancel_checkin(i, b))
        btn.bind("<Enter>",    lambda e, b=btn: b.config(bg="#64748b"))
        btn.bind("<Leave>",    lambda e, b=btn: b.config(bg="#94a3b8"))
        notify("✅ 입실 완료",
               f"{item.get('rpName','')}\n{item.get('rrBooker','')}님 입실 "
               f"({datetime.now().strftime('%H:%M')})")

    def _on_cancel_checkin(self, item, btn):
        rr_seq = item.get("rrSeq", "")
        self.checkin_set.discard(rr_seq)
        btn.config(text="입실", bg="#2563eb", cursor="hand2")
        btn.bind("<Button-1>", lambda e, i=item, b=btn: self._on_checkin(i, b))
        btn.bind("<Enter>",    lambda e, b=btn: b.config(bg="#1d4ed8"))
        btn.bind("<Leave>",    lambda e, b=btn: b.config(bg="#2563eb"))

    # ── 20분 타이머 ──────────────────────────────────────────────────────────

    def _timer_tick(self):
        now = datetime.now()
        for item in self.items:
            if item.get("rrState") != "예약완료":
                continue
            rr_seq = item.get("rrSeq", "")
            if rr_seq in self.checkin_set or rr_seq in self.alerted_set:
                continue
            try:
                h, m = map(int, item["rrStartTime"].split(":"))
                deadline = now.replace(hour=h, minute=m, second=0, microsecond=0) \
                           + timedelta(minutes=20)
            except (ValueError, KeyError):
                continue
            if now >= deadline:
                self.alerted_set.add(rr_seq)
                notify("⚠️ 미입실 알림",
                       f"{item.get('rpName','')}\n{item.get('rrBooker','')}님이 "
                       f"{item['rrStartTime']} 예약 후 입실하지 않았습니다.")
        self.root.after(30_000, self._timer_tick)


def main():
    root = tk.Tk()
    StudioApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
