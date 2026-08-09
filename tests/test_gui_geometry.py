from lol_coach.config import clamp_window_geometry


def test_clamp_window_geometry_keeps_saved_window_on_screen() -> None:
    assert (
        clamp_window_geometry("960x1008+1928+21", screen_width=1920, screen_height=1080)
        == "960x1008+960+21"
    )
