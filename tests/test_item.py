import pytest

from app.models.item import Item, ItemBuild, MAX_ITEM_SLOTS


def test_load_all_items():
    items = Item.load_all()
    assert "3031" in items
    assert items["3031"].name == "무한의 대검"
    assert items["3031"].attack_damage == 65.0
    assert items["3031"].crit_chance == 0.25


def test_item_build_aggregates_stats():
    items = Item.load_all()
    build = ItemBuild()
    build.add(items["3031"])  # 무한의 대검
    build.add(items["3072"])  # 피바라기

    totals = build.total_stats()
    assert totals["FlatPhysicalDamageMod"] == 65.0 + 55.0
    assert totals["FlatCritChanceMod"] == 0.25 + 0.20


def test_item_build_enforces_max_slots():
    items = list(Item.load_all().values())
    build = ItemBuild()
    for item in (items * 2)[:MAX_ITEM_SLOTS]:
        build.add(item)

    with pytest.raises(ValueError):
        build.add(items[0])


def test_only_doran_items_are_starters():
    starters = {item.name for item in Item.load_all().values() if item.is_starter}
    assert starters == {"도란의 검", "도란의 활"}


def test_level_estimate_counts_only_completed_items():
    counted = {item.name for item in Item.load_all().values() if item.counts_for_level_estimate}
    assert counted == {"무한의 대검", "크라켄의 슬레이어", "피바라기", "루난의 허리케인"}


def test_infinity_edge_crit_damage_bonus_does_not_stack():
    items = Item.load_all()
    assert items["3031"].crit_damage_bonus == 0.30
    assert items["3072"].crit_damage_bonus == 0.0

    build = ItemBuild()
    assert build.crit_damage_bonus() == 0.0
    build.add(items["3031"])
    build.add(items["3031"])
    assert build.crit_damage_bonus() == 0.30
