import pytest

from app.models.item import Item, ItemBuild, MAX_ITEM_SLOTS


def test_load_all_items():
    items = Item.load_all()
    assert "3031" in items
    assert items["3031"].name == "무한의 대검"
    assert items["3031"].attack_damage == 75.0
    assert items["3031"].crit_chance == 0.25


def test_item_build_aggregates_stats():
    items = Item.load_all()
    build = ItemBuild()
    build.add(items["3031"])  # 무한의 대검
    build.add(items["3072"])  # 피바라기

    totals = build.total_stats()
    assert totals["FlatPhysicalDamageMod"] == 75.0 + 80.0
    assert totals["FlatCritChanceMod"] == 0.25  # 피바라기는 16.19.1 기준 치명타 없음


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
    assert counted == {
        "무한의 대검", "크라켄 학살자", "피바라기", "루난의 허리케인", "삼위일체", "선체파괴자",
        "도미닉 경의 인사", "불멸의 철갑궁", "유령 무희", "래피드파이어 대포", "스톰레이저",
        "나보리 신속검", "악마사냥꾼의 화살", "헥스옵틱 C44", "필멸자의 운명", "징수의 총", "정수 약탈자",
    }


CRIT_ITEM_IDS = {
    "3036", "3031", "6673", "3046", "3094", "3085", "3095",
    "6675", "2512", "2523", "3033", "6676", "3508",
}  # metabot.gg 패치 26.20 치명타 확률 아이템 13종


def test_all_crit_chance_items_are_included():
    items = Item.load_all()
    assert CRIT_ITEM_IDS <= set(items)
    for item_id in CRIT_ITEM_IDS:
        assert items[item_id].crit_chance == 0.25, items[item_id].name


def test_only_listed_items_have_crit_chance():
    items = Item.load_all()
    assert {i.id for i in items.values() if i.crit_chance > 0} == CRIT_ITEM_IDS


def test_infinity_edge_crit_damage_bonus_does_not_stack():
    items = Item.load_all()
    assert items["3031"].crit_damage_bonus == 0.30
    assert items["3072"].crit_damage_bonus == 0.0

    build = ItemBuild()
    assert build.crit_damage_bonus() == 0.0
    build.add(items["3031"])
    build.add(items["3031"])
    assert build.crit_damage_bonus() == 0.30
