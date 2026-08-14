from lol_coach.config import clamp_window_geometry


def test_clamp_keeps_window_on_secondary_monitor() -> None:
    """보조 모니터(오른쪽)에 저장된 창 위치가 보존되어야 한다."""
    # 가상 화면: 메인(0~1920) + 보조(1920~3840)
    result = clamp_window_geometry(
        "960x1008+2000+21",
        screen_width=1920,
        screen_height=1080,
        vscreen_x=0,
        vscreen_y=0,
        vscreen_width=3840,
        vscreen_height=1080,
    )
    assert result == "960x1008+2000+21"


def test_clamp_keeps_window_on_left_monitor() -> None:
    """보조 모니터(왼쪽, 음수 좌표)에 저장된 창 위치가 보존되어야 한다."""
    # 가상 화면: 보조(-1920~0) + 메인(0~1920)
    result = clamp_window_geometry(
        "960x1008-1500+21",
        screen_width=1920,
        screen_height=1080,
        vscreen_x=-1920,
        vscreen_y=0,
        vscreen_width=3840,
        vscreen_height=1080,
    )
    assert result == "960x1008-1500+21"


def test_clamp_fallback_when_completely_offscreen() -> None:
    """가상 화면을 완전히 벗어난 창은 메인 모니터 (0,0)로 fallback."""
    result = clamp_window_geometry(
        "960x1008+99999+99999",
        screen_width=1920,
        screen_height=1080,
        vscreen_x=0,
        vscreen_y=0,
        vscreen_width=3840,
        vscreen_height=1080,
    )
    assert result == "960x1008+0+0"


def test_clamp_fallback_without_virtual_screen() -> None:
    """가상 화면 정보 없으면 메인 모니터만 사용 — 화면 밖은 fallback."""
    # vscreen 미지정 → vw=screen_width=1920, x=2000은 밖이므로 fallback
    result = clamp_window_geometry(
        "960x1008+2000+21",
        screen_width=1920,
        screen_height=1080,
    )
    assert result == "960x1008+0+0"


def test_clamp_keeps_main_monitor_position() -> None:
    """메인 모니터 안의 창은 그대로 유지."""
    result = clamp_window_geometry(
        "960x1008+100+21",
        screen_width=1920,
        screen_height=1080,
        vscreen_x=0,
        vscreen_y=0,
        vscreen_width=3840,
        vscreen_height=1080,
    )
    assert result == "960x1008+100+21"


def test_clamp_invalid_geometry_fallback() -> None:
    """잘못된 geometry 형식은 기본값."""
    assert clamp_window_geometry("garbage", screen_width=1920, screen_height=1080) == "1120x920+0+0"
