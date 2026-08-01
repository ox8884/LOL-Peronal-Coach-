from lol_coach.ugg.counters import CounterClient

SAMPLE_HTML = """
<html><body>
<h1>Ahri Counter for Mid Patch 26.13</h1>
<div>Best Lane Counters vs Ahri
These picks counter Ahri during early game laning phase. Highest gold differential at 15 (GD@15) vs Ahri in World Emerald +.
Irelia
+817 GD15
2,589
games
Zed
+488 GD15
8,015
games
Fizz
+395 GD15
5,426
games
Kassadin
-347 GD15
3,267
games
</div>
</body></html>
"""


def test_parse_lane_counters():
    client = CounterClient.__new__(CounterClient)
    report = CounterClient._parse(
        client,
        SAMPLE_HTML,
        enemy="Ahri",
        role="mid",
        url="https://u.gg/test",
        limit=10,
        min_matches=500,
    )
    assert report.patch == "26.13"
    assert len(report.lane_counters) >= 3
    assert report.lane_counters[0].champion == "Irelia"
    assert report.lane_counters[0].gd15 == 817
    assert report.hard_matchups
    assert report.hard_matchups[0].gd15 < 0
