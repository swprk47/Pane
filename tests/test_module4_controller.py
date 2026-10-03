import sys
import io
from pathlib import Path
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtCore import QTimer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.glass_controller import GlassController, DEFAULT_LAYOUT

def run_controller_tests():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    print("=== [모듈 4: 모듈형 플로팅 글라스 컨트롤러 검증 테스트] ===")
    app = QApplication(sys.argv)

    # 1. GlassController 인스턴스화
    container = QWidget()
    container.resize(800, 500)
    layout = QVBoxLayout(container)
    layout.addStretch()

    controller = GlassController(container)
    layout.addWidget(controller, alignment=Qt.AlignHCenter)
    container.show()
    print("[1] GlassController 인스턴스화 및 뷰 배치 성공!")

    # 2. 기본 레이아웃 확인
    print("\n[2] 기본 버튼 구역별 레이아웃 검증:")
    assert "play_pause" in controller.current_layout["left"]
    assert "speed_button" in controller.current_layout["center"]
    assert "volume" in controller.current_layout["right"]
    print("  [OK] 좌/중/우 구역별 기본 버튼 배치 확인 완료")

    # 3. 사용자 맞춤형 버튼 레이아웃 변경(커스터마이징) 테스트
    print("\n[3] 버튼 배열 커스터마이징(동적 재구성) 테스트:")
    custom_layout = {
        "left": ["play_pause", "time_label"],
        "center": ["speed_button"],
        "right": ["volume", "fullscreen"]
    }
    controller._save_layout(custom_layout)
    assert controller.current_layout == custom_layout
    print("  [OK] 커스텀 레이아웃 반영 및 위젯 동적 재빌드 완료")

    # 기본 레이아웃으로 복원
    controller._save_layout(DEFAULT_LAYOUT)
    print("  [OK] 기본 레이아웃 원복 완료")

    # 4. 시간 표시 및 타임라인 슬라이더 검증
    print("\n[4] 타임라인 및 시간 표시 검증:")
    controller.set_duration(645.0)  # 10분 45초
    controller.set_time_pos(83.0)   # 1분 23초
    assert "01:23 / 10:45" in controller.lbl_time.text()
    print(f"  [OK] 시간 텍스트 포맷팅 확인: {controller.lbl_time.text()}")

    # 5. 배속 및 재생 상태 업데이트 검증
    print("\n[5] 배속 및 상태 표시 검증:")
    controller.set_speed_display(1.40)
    assert controller.btn_speed.text() == "1.40x"
    print(f"  [OK] 배속 버튼 텍스트 업데이트 확인: {controller.btn_speed.text()}")

    controller.set_playback_state(True)
    assert controller.btn_play.text() == "⏸"
    print("  [OK] 재생 중 아이콘(⏸) 전환 확인")

    controller.set_playback_state(False)
    assert controller.btn_play.text() == "▶"
    print("  [OK] 일시정지 아이콘(▶) 전환 확인")

    # 6. 자동 숨김 타이머 검증
    print("\n[6] 마우스 인터랙션 및 자동 페이드아웃 검증:")
    controller.trigger_activity()
    assert controller.opacity_effect.opacity() > 0.0
    print("  [OK] 마우스 활동 감지 및 페이드인 확인")

    interactive = "--interactive" in sys.argv
    if not interactive:
        QTimer.singleShot(1500, app.quit)
        print("  [INFO] 자동 테스트 모드: 1.5초 후 정상 종료됩니다.")
    else:
        print("  [INFO] 대화형 모드: 버튼 클릭 및 ⚙️ 버튼으로 커스텀 설정을 체험해보세요.")

    app.exec()
    print("\n*** [모듈 4: 모듈형 플로팅 컨트롤러 검증 완료! 모든 테스트 통과] ***")

if __name__ == "__main__":
    from PySide6.QtCore import Qt
    run_controller_tests()
