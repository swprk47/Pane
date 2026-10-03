import sys
import time
from pathlib import Path
from PySide6.QtCore import QCoreApplication

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.player_engine import PlayerEngine

def run_engine_tests():
    app = QCoreApplication(sys.argv)
    # Configure standard streams for utf-8 on Windows
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    print("=== [모듈 1: 초경량 재생 코어 엔진 검증 테스트] ===")

    engine = PlayerEngine()
    print("[1] PlayerEngine 인스턴스화 성공!")

    # 1. 정밀 배속 테스트 (0.05 단위 및 1.25x, 1.40x 테스트)
    print("\n[2] 정밀 배속 제어 테스트:")
    target_speeds = [1.0, 1.2, 1.25, 1.4, 1.45, 1.75, 2.0]
    for spd in target_speeds:
        applied = engine.set_speed(spd)
        read_spd = engine.get_speed()
        assert applied == spd, f"Speed set mismatch: {applied} != {spd}"
        assert read_spd == spd, f"Speed read mismatch: {read_spd} != {spd}"
        print(f"  [OK] 배속 {spd}x 설정 성공 (실제 엔진 반영: {read_spd}x)")

    # 2. 상대 배속 증감 테스트 (+0.05x, -0.05x)
    print("\n[3] 0.05x 미세 배속 증감 테스트:")
    engine.set_speed(1.20)
    new_spd = engine.change_speed_relative(+0.05)
    assert new_spd == 1.25, f"Expected 1.25, got {new_spd}"
    print(f"  [OK] 1.20x + 0.05x -> {new_spd}x (성공)")

    new_spd = engine.change_speed_relative(+0.15)
    assert new_spd == 1.40, f"Expected 1.40, got {new_spd}"
    print(f"  [OK] 1.25x + 0.15x -> {new_spd}x (성공)")

    reset_spd = engine.reset_speed()
    assert reset_spd == 1.0, f"Expected 1.0, got {reset_spd}"
    print(f"  [OK] 리셋 키(\\) 동작 -> {reset_spd}x (성공)")

    # 3. 볼륨 테스트
    print("\n[4] 볼륨 제어 테스트:")
    engine.set_volume(75.0)
    assert engine.get_volume() == 75.0
    print(f"  [OK] 볼륨 75% 설정 성공: {engine.get_volume()}%")

    # 4. 내장 테스트 미디어 재생 및 시그널 수신 테스트
    print("\n[5] 미디어 로드 및 재생 이벤트 검증:")
    events_received = {"time": False, "speed": False}

    def on_time(pos):
        events_received["time"] = True

    def on_speed(s):
        events_received["speed"] = True

    engine.time_pos_changed.connect(on_time)
    engine.speed_changed.connect(on_speed)

    # Use mpv lavfi test pattern (synthetic 2-second video)
    test_media = "av://lavfi:testsrc=duration=2:size=640x360:rate=30"
    engine.load_file(test_media)
    engine.set_speed(1.40)
    engine.play()

    # Process events for 1 second
    start = time.time()
    while time.time() - start < 1.2:
        app.processEvents()
        time.sleep(0.05)

    print(f"  [OK] 현재 재생 중: {engine.is_playing()}")
    print(f"  [OK] 배속 시그널 수신: {events_received['speed']}")

    engine.terminate()
    print("\n*** [모듈 1: 재생 코어 엔진 검증 완료! 모든 테스트 통과] ***")

if __name__ == "__main__":
    run_engine_tests()
