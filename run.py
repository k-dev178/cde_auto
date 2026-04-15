#!/usr/bin/env python3
"""CDE 스튜디오 서버 실행기 — macOS / Windows 공통"""
import os
import sys
import time
import threading
import subprocess
import webbrowser
import socket
import urllib.request

PORT = 80
URL  = f"http://localhost:{PORT}"
HERE = os.path.dirname(os.path.abspath(__file__))


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def kill_port(port: int):
    subprocess.call(
        ["powershell", "-Command",
         f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
         f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"]
    )
    time.sleep(1)


def wait_ready(url: str, timeout: int = 15) -> bool:
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def start_server():
    if port_in_use(PORT):
        print(f"포트 {PORT} 사용 중. 기존 서버를 종료합니다...")
        kill_port(PORT)
        print("기존 서버 종료 완료.")

    print(f"서버를 시작합니다 (포트 {PORT})...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=HERE,
    )

    if not wait_ready(URL):
        print("서버 시작에 실패했습니다.")
        proc.terminate()
        sys.exit(1)

    print(f"서버 준비 완료 → {URL}")
    return proc


def main():
    os.chdir(HERE)
    proc = start_server()
    webbrowser.open(URL)
    print("명령어: reboot(재시작)  |  종료: Ctrl+C")

    restart_flag = threading.Event()

    def input_loop():
        while True:
            try:
                cmd = input().strip().lower()
            except EOFError:
                break
            if cmd == "reboot":
                print("재시작합니다...")
                restart_flag.set()
                proc.terminate()
                break

    t = threading.Thread(target=input_loop, daemon=True)
    t.start()

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
        proc.terminate()
        proc.wait()
        return

    if restart_flag.is_set():
        proc.wait()
        main()


if __name__ == "__main__":
    main()
