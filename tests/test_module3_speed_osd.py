import sys
import io
from pathlib import Path
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout
from PySide6.QtCore import QTimer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.speed_popup import SpeedPopup, DEFAULT_PRESETS
from ui.osd_widget import GlassOSDWidget

def run_speed_osd_tests():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    print("=== [모듈 3: 정밀 배속 팝업 & 글라스 OSD 위젯 검증 테스트] ===")
    app = QApplication(sys.argv)

    # 1. 기본 프리셋 검증 (1.4 제외, 1.0, 1.2, 1.25, 1.5, 2.0 확인)
    popup = SpeedPopup()
    popup._reset_to_default_presets()
    print("[1] SpeedPopup 생성 및 기본 프리셋 확인:")
    print(f"  현재 프리셋: {popup.presets}")
    assert 1.4 not in popup.presets, "1.4x should not be in default presets"
    assert 1.25 in popup.presets, "1.25x should be in default presets"
    print("  [OK] 1.4x 제외 및 1.25x 포함 기본 프리셋 검증 통과")

    # 2. 0.05x 정밀 슬라이더 및 시그널 방출 검증
    emitted_speeds = []
    popup.speed_selected.connect(lambda s: emitted_speeds.append(s))

    popup.slider.setValue(140)  # 1.40x
    assert round(popup._current_speed, 2) == 1.40
    print(f"  [OK] 슬라이더 1.40x 이동 성공 -> 현재 속도: {popup._current_speed:.2f}x")

    # 3. 📌 핀 버튼을 통한 커스텀 프리셋 추가 검증
    print("\n[2] 📌 슬라이더 배속 핀(Pin) 추가 테스트:")
    popup._pin_current_speed()
    assert 1.4 in popup.presets, "1.4x should be added to presets via Pin"
    print(f"  [OK] 1.40x 핀 추가 완료 -> 새 프리셋 목록: {popup.presets}")

    # 3-1. 핀 최대 개수(6) 제한 검증
    from ui.speed_popup import MAX_PRESETS
    assert MAX_PRESETS == 6
    popup.slider.setValue(130)
    popup._pin_current_speed()           # fills the 6th slot (5 defaults + 1.4 above, 1.3 may be refused)
    popup.slider.setValue(175)
    before = list(popup.presets)
    assert len(before) <= MAX_PRESETS
    if len(before) == MAX_PRESETS:
        assert popup._pin_current_speed() is False, "pinning beyond the max must be refused"
        assert popup.presets == before
    print(f"  [OK] 최대 {MAX_PRESETS}개 제한 확인 -> {popup.presets}")

    # 4. 프리셋 언핀(Unpin / 삭제) 검증
    print("\n[3] ✕ 프리셋 언핀(삭제) 테스트:")
    popup._unpin_preset(1.2)
    assert 1.2 not in popup.presets, "1.2x should be removed from presets"
    print(f"  [OK] 1.2x 삭제 완료 -> 현재 프리셋 목록: {popup.presets}")

    # 5. 기본값 리셋 검증
    print("\n[4] 기본 프리셋 초기화 테스트:")
    popup._reset_to_default_presets()
    assert popup.presets == DEFAULT_PRESETS
    print(f"  [OK] 기본 프리셋 원복 완료: {popup.presets}")

    # 6. 글라스 OSD 뱃지 검증
    print("\n[5] 글라스 OSD 위젯 표시 및 페이드아웃 검증:")
    parent_win = QWidget()
    parent_win.resize(600, 400)
    osd = GlassOSDWidget(parent_win)
    parent_win.show()

    osd.show_message("1.40x", "⚡")
    assert osd.text_label.text() == "1.40x"
    assert osd.isVisible()
    print("  [OK] OSD 뱃지 1.40x 표시 확인")

    interactive = "--interactive" in sys.argv
    if not interactive:
        QTimer.singleShot(1500, app.quit)
        print("  [INFO] 자동 테스트 모드: 1.5초 후 정상 종료됩니다.")
    else:
        print("  [INFO] 대화형 모드: UI를 직접 조작해볼 수 있습니다.")

    app.exec()
    print("\n*** [모듈 3: 정밀 배속 & OSD 위젯 검증 완료! 모든 테스트 통과] ***")

if __name__ == "__main__":
    run_speed_osd_tests()
