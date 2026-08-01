from lol_coach.modes import (
    QUEUE_ARAM,
    QUEUE_ARAM_MAYHEM,
    display_mode_for_queue,
    normalize_mode,
    queues_for_mode,
)


def test_normalize_mode_aliases():
    assert normalize_mode("summoners_rift") == "summoners_rift"
    assert normalize_mode("sr") == "summoners_rift"
    assert normalize_mode("aram") == "aram"
    assert normalize_mode("mayhem") == "aram"
    assert normalize_mode("ARAM_MAYHEM") == "aram"


def test_queue_labels():
    assert display_mode_for_queue(QUEUE_ARAM) == "ARAM"
    assert display_mode_for_queue(QUEUE_ARAM_MAYHEM) == "ARAM Mayhem"
    assert display_mode_for_queue(420) == "Ranked Solo"


def test_queues_for_mode_includes_mayhem():
    aram_q = queues_for_mode("aram")
    assert aram_q is not None
    assert QUEUE_ARAM in aram_q
    assert QUEUE_ARAM_MAYHEM in aram_q
