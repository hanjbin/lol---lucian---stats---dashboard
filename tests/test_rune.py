import pytest

from app.models.rune import RunePage, RuneTree


@pytest.fixture
def trees():
    return RuneTree.load_all()


def make_page(trees, primary, keystone, primary_keys, secondary, secondary_keys):
    p, s = trees[primary], trees[secondary]
    return RunePage(
        primary_tree=p,
        keystone=p.rune(keystone),
        primary_runes=tuple(p.rune(k) for k in primary_keys),
        secondary_tree=s,
        secondary_runes=tuple(s.rune(k) for k in secondary_keys),
    )


def test_tree_structure(trees):
    assert [t.name for t in trees.values()] == ["정밀", "지배", "마법", "영감"]
    assert all(t.allow_primary for t in trees.values())
    assert [t.key for t in trees.values() if t.allow_secondary] == [
        "Precision", "Domination", "Inspiration"
    ]
    for tree in trees.values():
        assert len(tree.slots) == 4  # 키스톤 + 슬롯 3개
        assert all(len(row) >= 1 for row in tree.slots)


def test_valid_page(trees):
    page = make_page(
        trees, "Precision", "PressTheAttack", ["Triumph", "LegendAlacrity", "CutDown"],
        "Domination", ["SuddenImpact", "TreasureHunter"],
    )
    assert [r.name for r in page.runes] == [
        "집중 공격", "승전보", "전설: 민첩함", "체력차 극복", "돌발 일격", "보물 사냥꾼"
    ]
    assert page.get("SuddenImpact").name == "돌발 일격"
    assert page.get("Conqueror") is None


def test_secondary_tree_must_differ_from_primary(trees):
    with pytest.raises(ValueError, match="달라야"):
        make_page(
            trees, "Precision", "PressTheAttack", ["Triumph", "LegendAlacrity", "CutDown"],
            "Precision", ["PresenceOfMind", "LegendHaste"],
        )


def test_sorcery_cannot_be_secondary(trees):
    with pytest.raises(ValueError, match="보조 룬으로 선택할 수 없"):
        make_page(
            trees, "Precision", "PressTheAttack", ["Triumph", "LegendAlacrity", "CutDown"],
            "Sorcery", ["NullifyingOrb", "Transcendence"],
        )


def test_sorcery_can_be_primary(trees):
    page = make_page(
        trees, "Sorcery", "ArcaneComet", ["NullifyingOrb", "Transcendence", "Scorch"],
        "Inspiration", ["MagicalFootwear", "JackOfAllTrades"],
    )
    assert page.keystone.name == "신비로운 유성"


def test_secondary_runes_must_come_from_different_rows(trees):
    with pytest.raises(ValueError, match="서로 다른 슬롯"):
        make_page(
            trees, "Precision", "PressTheAttack", ["Triumph", "LegendAlacrity", "CutDown"],
            "Domination", ["SuddenImpact", "TasteOfBlood"],
        )


def test_secondary_cannot_take_keystone(trees):
    with pytest.raises(ValueError, match="일반 슬롯 룬이 아닙니다"):
        make_page(
            trees, "Precision", "PressTheAttack", ["Triumph", "LegendAlacrity", "CutDown"],
            "Domination", ["Electrocute", "TreasureHunter"],
        )


def test_primary_runes_must_match_their_slot(trees):
    with pytest.raises(ValueError, match="슬롯에 속하지 않습니다"):
        make_page(
            trees, "Precision", "PressTheAttack", ["LegendAlacrity", "Triumph", "CutDown"],
            "Domination", ["SuddenImpact", "TreasureHunter"],
        )
