from app.models.opponent import Opponent, estimate_level_from_item_count


def test_load_opponent():
    opp = Opponent.load_by_id("generic_squishy")
    assert opp.armor == 30.0


def test_armor_grows_with_level():
    opp = Opponent.load_by_id("generic_squishy")
    assert opp.armor_at_level(18) > opp.armor_at_level(1)


def test_estimate_level_from_item_count_uses_range_midpoint():
    assert estimate_level_from_item_count(0) == 2
    assert estimate_level_from_item_count(1) == 7
    assert estimate_level_from_item_count(2) == 10
    assert estimate_level_from_item_count(3) == 12
    assert estimate_level_from_item_count(4) == 14
    assert estimate_level_from_item_count(5) == 16
    assert estimate_level_from_item_count(6) == 17


def test_estimate_level_from_item_count_clamps_out_of_range_counts():
    assert estimate_level_from_item_count(-1) == estimate_level_from_item_count(0)
    assert estimate_level_from_item_count(99) == estimate_level_from_item_count(6)
