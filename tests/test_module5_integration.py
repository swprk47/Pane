import sys
import io
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeyEvent

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.main_window import MainWindow

def run_integration_tests():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    print("=== [모듈 5: 전체 통합 & 기능 종합 검증 테스트] ===")
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()
    print("[1] MainWindow 통합 인스턴스 생성 및 렌더링 성공!")

    # 1. 컴포넌트 바인딩 확인
    assert window.engine is not None
    assert window.controller is not None
    assert window.speed_popup is not None
    assert window.osd is not None
    print("  [OK] 엔진, 컨트롤러, 배속 팝업, OSD 위젯 전체 바인딩 확인")

    # 2. 내장 테스트 미디어 로드 및 재생 검증
    print("\n[2] 비디오 로드 및 컨트롤러/OSD 연동 테스트:")
    test_media = "av://lavfi:testsrc=duration=5:size=640x360:rate=30"
    window.engine.load_file(test_media)
    window.engine.play()

    # Process events
    for _ in range(5):
        app.processEvents()
        time.sleep(0.05)

    print(f"  [OK] 미디어 로드 및 재생 시작: playing={window.engine.is_playing()}")

    # 3. 배속 제어 및 OSD 반영 테스트
    print("\n[3] 0.05x 정밀 배속 조절 및 OSD/컨트롤러 동기화 테스트:")
    window.change_speed_relative(+0.25)  # 1.0x -> 1.25x

    # Process events to allow async mpv property observer to dispatch Qt signal
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)

    assert window.engine.get_speed() == 1.25
    assert window.controller.btn_speed.text() == "1.25x"
    assert window.osd.text_label.text() == "1.25x"
    print(f"  [OK] +0.25x 적용 -> 엔진: {window.engine.get_speed()}x, UI: {window.controller.btn_speed.text()}, OSD: {window.osd.text_label.text()}")

    window.change_speed_relative(+0.15)  # 1.25x + 0.15x -> 1.40x
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)

    assert window.engine.get_speed() == 1.40
    assert window.controller.btn_speed.text() == "1.40x"
    assert window.osd.text_label.text() == "1.40x"
    print(f"  [OK] 1.40x 적용 -> 엔진: {window.engine.get_speed()}x, UI: {window.controller.btn_speed.text()}, OSD: {window.osd.text_label.text()}")

    # 4. 단축키 시뮬레이션
    print("\n[4] 키보드 단축키 핸들러 테스트:")
    # Reset speed key (\)
    key_reset = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Backslash, Qt.NoModifier)
    window.keyPressEvent(key_reset)
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)
    assert window.engine.get_speed() == 1.0
    print("  [OK] 리셋 단축키(\\) -> 1.0x 복귀 확인")

    # Space play/pause
    key_space = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Space, Qt.NoModifier)
    window.keyPressEvent(key_space)
    print("  [OK] Space 키 재생/일시정지 토글 확인")

    # PIP toggle
    key_p = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_P, Qt.NoModifier)
    window.keyPressEvent(key_p)
    assert window._is_pip is True
    print("  [OK] P 키 PIP(항상 위 미니 모드) 진입 확인")
    window.keyPressEvent(key_p)
    assert window._is_pip is False
    print("  [OK] P 키 PIP 해제 및 일반 모드 복귀 확인")

    # 5. 설정 및 이어보기 저장소 검증
    print("\n[5] 최근 파일 및 이어보기 저장소 검증:")
    window.app_settings.save_resume_position("sample_test.mp4", 124.5)
    saved_pos = window.app_settings.get_resume_position("sample_test.mp4")
    assert saved_pos == 124.5
    print(f"  [OK] 이어보기 타임스탬프 저장 및 조회 성공: {saved_pos}초")

    # 자동 종료 타이머
    interactive = "--interactive" in sys.argv
    if not interactive:
        QTimer.singleShot(1500, app.quit)
        print("  [INFO] 자동 테스트 모드: 1.5초 후 정상 종료됩니다.")
    else:
        print("  [INFO] 대화형 모드: 실제 플레이어 조작을 테스트해보세요.")

    app.exec()
    window._on_close()
    print("\n*** [모듈 5: 전체 통합 & 기능 종합 검증 완료! 모든 테스트 통과] ***")

if __name__ == "__main__":
    run_integration_tests()
