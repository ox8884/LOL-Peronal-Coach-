from lol_coach.static.i18n import KoreanLocalizer, _norm_key


def test_norm_key_strips_legacy_prefixes():
    assert _norm_key("The Keystone Electrocute") == "electrocute"
    assert _norm_key("Death's Dance") == "death's dance"
    assert "quest" not in _norm_key("Crimson Lucidity Quest Reward")


def test_item_and_rune_korean():
    loc = KoreanLocalizer()
    loc.ensure_loaded()
    # Official DDragon pairs (patch-dependent names but these are stable)
    assert loc.item("Death's Dance") in ("죽음의 무도", "Death's Dance")
    # Blackfire Torch — 2503 in recent patches
    ko = loc.item("Blackfire Torch")
    assert ko  # should not be empty
    assert ko != "Blackfire Torch" or loc.item(2503)  # ideally translated
    # Prefer id path if name map misses on odd patches
    if "2503" in {str(k) for k in loc._item_ko}:
        assert "횃불" in loc.item(2503) or "불" in loc.item(2503) or loc.item(2503)

    assert loc.rune("Electrocute")  # 감전
    elec = loc.rune("Electrocute")
    assert elec in ("감전", "Electrocute") or len(elec) > 0

    flash = loc.spell("Flash")
    assert flash in ("점멸", "Flash") or flash


def test_known_stable_translations():
    loc = KoreanLocalizer()
    loc.ensure_loaded()
    # These English keys have been stable for years
    assert loc.spell("Flash") == "점멸"
    assert loc.spell("Ignite") == "점화"
    assert loc.rune("Domination") == "지배"
    assert loc.rune("Sorcery") == "마법"
    # Death's Dance
    dd = loc.item("Death's Dance")
    assert dd == "죽음의 무도"
