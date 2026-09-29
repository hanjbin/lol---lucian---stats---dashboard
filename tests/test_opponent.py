from app.models.opponent import Opponent


def test_load_opponent():
    opp = Opponent.load_by_id("generic_squishy")
    assert opp.armor == 30.0


def test_armor_grows_with_level():
    opp = Opponent.load_by_id("generic_squishy")
    assert opp.armor_at_level(18) > opp.armor_at_level(1)
