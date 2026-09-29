import pytest

from app.models.champion import Champion
from app.models.item import Item, ItemBuild
from app.models.opponent import Opponent
from app.models.rune import Rune
from app.services.damage_calculator import (
    combine_stats,
    damage_after_resist,
    expected_auto_attack_damage,
    auto_attack_dps,
)


def test_combine_stats_with_no_items_or_runes_matches_base_champion():
    champ = Champion.load("Lucian")
    stats = champ.stats_at_level(1)
    combined = combine_stats(stats, ItemBuild())

    assert combined.attack_damage == champ.base_stats.attack_damage
    assert combined.attack_speed == stats.attack_speed
    assert combined.crit_chance == 0.0
    assert combined.life_steal_percent == 0.0


def test_combine_stats_adds_item_totals():
    champ = Champion.load("Lucian")
    stats = champ.stats_at_level(18)

    items = Item.load_all()
    build = ItemBuild()
    build.add(items["3031"])  # 무한의 대검: AD 65, 치명타 확률 0.25

    combined = combine_stats(stats, build)

    assert combined.attack_damage == stats.attack_damage + 65.0
    assert combined.crit_chance == 0.25


def test_combine_stats_ignores_conditional_runes():
    champ = Champion.load("Lucian")
    stats = champ.stats_at_level(1)
    runes = Rune.load_all()  # 기민한 발놀림(flat) + 정복자/일격필살(conditional)

    combined = combine_stats(stats, ItemBuild(), runes)

    # 정복자/일격필살은 조건부라 반영되지 않고, 기민한 발놀림의 공속만 반영됨
    expected_attack_speed = stats.attack_speed * (1 + 0.08)
    assert combined.attack_speed == expected_attack_speed


def test_damage_after_resist_reduces_with_positive_armor():
    assert damage_after_resist(100.0, 0.0) == 100.0
    assert damage_after_resist(100.0, 100.0) == 50.0


def test_damage_after_resist_amplifies_with_negative_armor():
    assert damage_after_resist(100.0, -50.0) > 100.0


def test_expected_auto_attack_damage_uses_opponent_armor():
    champ = Champion.load("Lucian")
    stats = champ.stats_at_level(18)
    combined = combine_stats(stats, ItemBuild())
    opponent = Opponent.load_by_id("generic_squishy")

    damage = expected_auto_attack_damage(combined, opponent, 18)
    armor = opponent.armor_at_level(18)
    assert damage == combined.attack_damage * 100 / (100 + armor)


def test_auto_attack_dps_scales_with_attack_speed():
    champ = Champion.load("Lucian")
    stats = champ.stats_at_level(18)
    combined = combine_stats(stats, ItemBuild())
    opponent = Opponent.load_by_id("generic_squishy")

    dps = auto_attack_dps(combined, opponent, 18)
    single_hit = expected_auto_attack_damage(combined, opponent, 18)
    assert dps == single_hit * combined.attack_speed


def test_crit_damage_is_200_percent_by_default_and_230_with_infinity_edge():
    stats = Champion.load("Lucian").stats_at_level(18)
    items = Item.load_all()
    assert combine_stats(stats, ItemBuild()).crit_damage == 2.0

    build = ItemBuild()
    build.add(items["3072"])  # 피바라기: 치명타 확률만 있고 치명타 피해량 증가 없음
    assert combine_stats(stats, build).crit_damage == 2.0

    build.add(items["3031"])  # 무한의 대검
    assert combine_stats(stats, build).crit_damage == pytest.approx(2.3)


def test_expected_crit_factor_is_weighted_average_of_normal_and_crit():
    stats = Champion.load("Lucian").stats_at_level(18)
    build = ItemBuild()
    build.add(Item.load_all()["3031"])  # 치명타 확률 25%, 치명타 피해량 230%
    combined = combine_stats(stats, build)

    normal = combined.attack_damage
    expected = normal * (1 - 0.25) + normal * 2.3 * 0.25
    assert combined.attack_damage * combined.expected_crit_factor == pytest.approx(expected)

    opponent = Opponent.load_by_id("generic_squishy")
    armor = opponent.armor_at_level(18)
    assert expected_auto_attack_damage(combined, opponent, 18) == pytest.approx(
        expected * 100 / (100 + armor)
    )
