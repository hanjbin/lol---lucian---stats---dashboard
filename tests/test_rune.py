from app.models.rune import Rune


def test_load_all_runes():
    runes = Rune.load_all()
    assert len(runes) == 3


def test_flat_stat_rune():
    rune = Rune.load_by_key("FleetFootwork")
    assert rune.type == "flat_stat"
    assert rune.is_conditional is False
    assert rune.stats["PercentAttackSpeedMod"] == 0.08


def test_conditional_rune_keeps_condition_data():
    rune = Rune.load_by_key("Conqueror")
    assert rune.is_conditional is True
    assert rune.condition["max_stacks"] == 5
