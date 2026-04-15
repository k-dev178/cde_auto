# CDE 스튜디오 대여 현황

CDE 스튜디오 예약 현황을 보여주는 웹 앱입니다.

## 설치

```bash
pip install -r requirements.txt
```

> 여러 Python 환경이 있는 경우, 실행할 Python의 pip로 설치해야 합니다.
> ```bash
> python -m pip install -r requirements.txt
> ```

## 실행

```bash
python -m uvicorn main:app --reload --port 8000
```

> `uvicorn` 단독 명령 대신 `python -m uvicorn`을 쓰면 현재 Python 환경에 설치된 패키지를 정확히 사용합니다.

브라우저에서 `http://localhost:8000` 접속

## 기능

| 기능 | 설명 |
|---|---|
| 예약 목록 | 오늘 날짜 예약 현황 자동 표시 |
| 자동 갱신 | 30초마다 최신 데이터로 갱신 |
| 입실 처리 | 입실 버튼 클릭으로 토글 |
| 미입실 알림 | 예약 시작 20분 후 미입실 시 브라우저 알림 |
| 엑셀 다운로드 | 월별 일별 예약 내역 `.xlsx` 다운로드 |

## 엑셀 다운로드

- 헤더의 월 선택 후 **엑셀 다운로드** 클릭
- URL 직접 호출: `/export?year=2026&month=4`
