import pytest

from app.models.item import Item, ItemBuild, MAX_ITEM_SLOTS


def test_load_all_items():
    items = Item.load_all()
    assert "3031" in items
    assert items["3031"].name == "무한의 검"
    assert items["3031"].attack_damage == 65.0
    assert items["3031"].crit_chance == 0.25


def test_item_build_aggregates_stats():
    items = Item.load_all()
    build = ItemBuild()
    build.add(items["3031"])  # 무한의 검
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
