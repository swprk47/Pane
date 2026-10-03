import sys
import os
import io
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.main_window import MainWindow

def run_window_test():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    print("=== [모듈 2: 애플 글라스 윈도우 프레임 검증 테스트] ===")
    app = QApplication(sys.argv)

    window = MainWindow()
    print("[1] MainWindow 인스턴스화 성공!")

    # 1. 렌더 서피스 확인 (mpv render API -> QOpenGLWidget, 별도 네이티브 창 없음)
    from ui.mpv_gl import MpvGLWidget
    assert isinstance(window.viewport, MpvGLWidget), "viewport must be the OpenGL render surface"
    assert window.viewport._mpv is window.engine.mpv, "mpv core must be attached to the viewport"
    print("  [OK] 비디오 렌더 서피스(QOpenGLWidget)에 mpv 코어 연결 확인")

    # 2. 타이틀바 및 컴포넌트 검증
    assert window.title_bar is not None
    print("  [OK] 커스텀 글라스 타이틀바 초기화 성공")
    window.title_bar.set_media_title("테스트_영상_샘플.mp4")
    assert "테스트_영상_샘플.mp4" in window.title_bar.file_label.text()
    print("  [OK] 미디어 타이틀 동적 업데이트 확인")

    # 3. 창 띄우기
    window.show()
    print("  [OK] 윈도우 11 프레임리스 글라스 창 표시 성공")

    # 자동 종료 타이머 (1.5초 후 테스트 통과 및 종료)
    # 직접 화면을 보고 싶다면: python tests/test_module2_window.py --interactive
    interactive = "--interactive" in sys.argv
    if not interactive:
        QTimer.singleShot(1500, app.quit)
        print("  [INFO] 자동 테스트 모드: 1.5초 후 정상 종료됩니다.")
    else:
        print("  [INFO] 대화형 모드: 창을 닫을 때까지 실행됩니다.")

    app.exec()
    print("\n*** [모듈 2: 애플 글라스 윈도우 프레임 검증 완료! 모든 테스트 통과] ***")

if __name__ == "__main__":
    run_window_test()
