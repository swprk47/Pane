# Pane

Windows 11용 개인 동영상 플레이어. 기존 플레이어에서 아쉬웠던 **배속 제한을 없애고**(0.05x 단위),
영상 위에 얹히는 유리 느낌의 컨트롤을 쓰는 가벼운 데스크톱 앱입니다.

> 현재 지인 공유 단계(v1.0.0)입니다. 라이선스는 아직 정하지 않았습니다.

## 주요 기능

- **0.05x 단위 정밀 배속** (피치 보정): 프리셋 최대 6개, 칩별 삭제, 현재 배속 핀 고정, 슬라이더
- **영상 위 오버레이 컨트롤**: 마우스를 2.5초 안 움직이면 사라지고 얇은 진행선만 남음
- 영상 클릭으로 재생/정지, 더블클릭으로 전체화면
- 이어보기, 최근 파일, PIP(항상 위 작은 창), 자막 자동 로드, 1프레임 이동, 화면 캡처
- `I` 키로 재생 정보: 코덱, GPU/CPU 디코딩 여부, 해상도, FPS, 버려진 프레임
- **연속 시청**: 영상이 끝나면 같은 폴더의 다음 영상(파일 이름 자연 정렬: `강의2` 다음이 `강의10`)을 3초 안내 뒤 자동 재생. 안내 중 `취소`/`Esc`로 머물거나 `지금 재생`. 우클릭 메뉴에서 끌 수 있음
- 우클릭 메뉴, 컨트롤 버튼 배치 설정

## 설치

설치 프로그램(`Pane-<버전>-setup.exe`)을 실행하면 됩니다. 관리자 권한은 필요 없고 내 계정에만 설치됩니다.
영상 파일의 "연결 프로그램" 목록에 등록할 수 있으며, 기존 기본 플레이어는 바꾸지 않습니다.

코드 서명이 없어서 처음 실행할 때 "Windows의 PC 보호" 창이 뜰 수 있습니다. **추가 정보 → 실행**을 누르세요.

요구 사항: Windows 11 (64비트). 그래픽 드라이버가 최신이면 하드웨어 디코딩으로 더 가볍게 재생됩니다.

## 단축키

| 키 | 동작 |
| --- | --- |
| `Space` | 재생 / 일시정지 |
| `]` `[` | 배속 +0.1 / -0.1 (`Shift`와 함께: 0.05) |
| `\` 또는 `Backspace` | 배속 1.0x로 되돌리기 |
| `←` `→` | 5초 이동 (`Shift`와 함께: 1초) |
| `,` `.` | 1프레임 뒤 / 앞 (일시정지 중) |
| `Shift+,` `Shift+.` (또는 `PageUp` `PageDown`) | 이전 / 다음 영상 |
| `↑` `↓` | 볼륨 +5 / -5 |
| `M` | 음소거 |
| `C` | 자막 켜기 / 끄기 |
| `F` 또는 `Enter` | 전체화면 |
| `P` | PIP 모드 |
| `I` | 재생 정보 |
| `Ctrl+O` | 파일 열기 |
| `Ctrl+S` | 화면 캡처 (바탕화면에 저장) |
| `Esc` | 다음 영상 안내 취소 / 패널 닫기 / 전체화면 나가기 / PIP 나가기 |

## 알려진 한계

- 4K 60fps 영상을 전체화면으로 볼 때 프레임이 약 5~8% 빠질 수 있음 (창 모드와 24~30fps 영상은 문제없음)
- 전체화면 진입 시 0.2초쯤 멈칫함
- 자막 싱크 조절, 오디오 트랙 선택은 아직 없음
- 파일 연결로 여러 영상을 한꺼번에 열면 첫 파일만 열림
- 코드 서명 없음, 다른 PC에서의 실행 시험은 아직 충분하지 않음

## 설정과 로그

- 설정(이어보기 위치, 최근 파일, 배속 프리셋, 컨트롤 배치, 볼륨)은 레지스트리 `HKEY_CURRENT_USER\Software\Pane`에 저장됩니다.
- 오류 기록: `%LOCALAPPDATA%\Pane\pane.log`

## 개발

Python 3.14, PySide6, python-mpv(libmpv 렌더 API → `QOpenGLWidget`), pywinstyles를 사용합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe tools\setup_mpv.py        # libmpv 내려받기 (lib/mpv)
.\.venv\Scripts\python.exe main.py "영상경로.mp4"     # 실행
.\.venv\Scripts\python.exe -m pytest                  # 테스트
.\.venv\Scripts\python.exe -m pytest --run-e2e        # 실제 마우스 입력 포함 (커서가 움직임)
.\.venv\Scripts\python.exe tools\build_release.py --installer   # dist/에 zip과 설치 프로그램 생성
```

설치 프로그램을 만들려면 Inno Setup 6이 필요합니다 (`winget install JRSoftware.InnoSetup`).

문서: [PROJECT_PLAN.md](PROJECT_PLAN.md)(계획과 구조), [PROGRESS.md](PROGRESS.md)(현재 상태와 다음 할 일), [docs/HISTORY.md](docs/HISTORY.md)(상세 이력), [CHANGELOG.md](CHANGELOG.md)(버전별 변경).

## 라이선스

아직 정하지 않았습니다. 재생 엔진 libmpv의 빌드 라이선스를 확인한 뒤 정할 예정이며, 그 전까지는
`release/LICENSE.txt`의 임시 약관(개인·비상업, 재배포 금지)이 적용됩니다.
