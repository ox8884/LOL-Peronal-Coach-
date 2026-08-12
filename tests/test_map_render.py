from lol_coach.analysis.killmap import build_kill_map
from lol_coach.gui.map_render import render_collapse_snapshot, render_kill_minimap

MATCH = {
    "info": {
        "participants": [
            {"participantId": 1, "teamId": 100, "championId": 103, "championName": "Ahri"},
            {"participantId": 2, "teamId": 100, "championId": 64, "championName": "LeeSin"},
            {"participantId": 3, "teamId": 200, "championId": 238, "championName": "Zed"},
            {"participantId": 4, "teamId": 200, "championId": 412, "championName": "Thresh"},
        ]
    }
}


def _dark_base(size: int):
    from PIL import Image

    return Image.new("RGBA", (size, size), (22, 26, 34, 255))


def _killmap():
    tl = {
        "info": {
            "frames": [
                {
                    "timestamp": 60000,
                    "participantFrames": {
                        "1": {"position": {"x": 1000, "y": 1000}},
                        "2": {"position": {"x": 2000, "y": 1000}},
                        "3": {"position": {"x": 7000, "y": 7000}},
                        "4": {"position": {"x": 7100, "y": 6900}},
                    },
                    "events": [
                        {"type": "CHAMPION_KILL", "timestamp": 30000, "killerId": 3, "victimId": 1, "position": {"x": 1500, "y": 1500}},
                        {"type": "CHAMPION_KILL", "timestamp": 35000, "killerId": 1, "victimId": 4, "position": {"x": 6900, "y": 7000}},
                        {"type": "CHAMPION_KILL", "timestamp": 40000, "killerId": 4, "victimId": 2, "position": {"x": 4000, "y": 3000}},
                        {"type": "CHAMPION_KILL", "timestamp": 55000, "killerId": 3, "victimId": 1, "position": {"x": 7200, "y": 6800}},
                    ],
                }
            ]
        }
    }
    return build_kill_map(tl, MATCH, my_participant_id=1)


def test_render_kill_minimap_draws_markers() -> None:
    data = _killmap()
    img = render_kill_minimap(data, _dark_base(512), size=320)

    assert img.size == (320, 320)
    # 마커가 맵 전체에 흩어져 그려지므로 bbox는 넓은 범위를 덮는다
    bbox = img.getbbox()
    assert bbox is not None
    assert bbox[2] - bbox[0] > 100


def test_render_collapse_snapshot_returns_image_when_collapse_exists() -> None:
    data = _killmap()
    assert data.collapse is not None
    assert data.collapse.timestamp == 55000

    img = render_collapse_snapshot(data, _dark_base(512), size=340)
    assert img is not None
    assert img.size == (340, 340)


def test_render_collapse_snapshot_none_without_collapse() -> None:
    from lol_coach.analysis.killmap import KillMapData

    data = KillMapData(my_kills=[], my_deaths=[], collapse=None)
    assert render_collapse_snapshot(data, _dark_base(512)) is None
