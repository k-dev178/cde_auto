# CDE Studio

전주대 CDE 스튜디오 예약 확인용 Windows 데스크톱 앱입니다.

## 개발 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```powershell
.\start_app.bat
```

## exe 실행

빌드된 단일 실행 파일은 아래 경로에 생성됩니다.

```text
dist\CDEStudio.exe
```

`CDEStudio.exe` 파일만 복사해서 실행해도 됩니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

## 저장되는 설정

- 다크/화이트 모드
- 셀프(1인)스튜디오 필터
- 왼쪽 룸 목록 열림 상태
- 백그라운드 실행 허용
- 알림 범위
- 입실 버튼 체크 상태
- 준비 버튼 체크 상태

설정과 상태는 임시 파일에 저장한 뒤 교체해 기존 파일 손상을 방지합니다.
깨진 JSON 파일을 발견하면 같은 폴더에 `*.corrupt-날짜-시간`으로 원본을 보관하고 기본값으로 복구합니다.

## 설정 초기화

exe로 실행한 앱의 설정과 상태는 아래 폴더에 저장됩니다.
설정을 전부 초기화하려면 앱을 종료한 뒤 이 폴더를 삭제하면 됩니다.

```text
C:\Users\{user명}\AppData\Local\CDEStudio
```

개발 모드에서 `start_app.bat`로 실행한 경우에는 repo 안의 아래 파일/폴더를 삭제하면 됩니다.

```text
config\client.json
data\room_state.json
```
