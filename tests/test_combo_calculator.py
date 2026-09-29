import pytest

from app.models.opponent import Opponent
from app.models.skill import ChampionKit
from app.services.combo_calculator import (
    AUTO_ATTACK,
    EMPOWERED_AUTO_ATTACK,
    burst_combo,
    dps_combo,
)
from app.services.damage_calculator import CombinedStats


def _stats(attack_speed=1.0, ability_haste=0.0):
    return CombinedStats(
        attack_damage=100.0,
        bonus_attack_damage=0.0,
        attack_speed=attack_speed,
        crit_chance=0.0,
        life_steal_percent=0.0,
        ability_haste=ability_haste,
    )


@pytest.fixture
def kit():
    return ChampionKit.load()


@pytest.fixture
def opponent():
    return Opponent.load_by_id("generic_squishy")


def _actions(result):
    return [(e.time, e.action) for e in result.events]


def test_dps_combo_without_haste(kit, opponent):
    # 레벨 18: Q 쿨 5초, W 쿨 10초, E 쿨 14초 -> 5초 안에 각 스킬 1회씩만 사용
    # 공속 1.0 -> 평타 t=0,1,2,3,4 (5회), 앞의 3회만 패시브 적용
    result = dps_combo(kit, 18, _stats(), opponent, 18)

    assert _actions(result) == [
        (0.0, "E"), (0.0, EMPOWERED_AUTO_ATTACK),
        (0.0, "Q"), (1.0, EMPOWERED_AUTO_ATTACK),
        (1.0, "W"), (2.0, EMPOWERED_AUTO_ATTACK),
        (3.0, AUTO_ATTACK),
        (4.0, AUTO_ATTACK),
    ]
    assert result.dps == pytest.approx(result.total_damage / 5.0)


def test_dps_combo_recasts_skill_when_cooldown_returns(kit, opponent):
    # 스킬 가속 100 -> Q 쿨 2.5초: t=0에 쓰고 t=2.5에 다시 사용, 다음 평타(t=3)에 패시브 적용
    result = dps_combo(kit, 18, _stats(ability_haste=100), opponent, 18)

    assert result.count("Q") == 2
    assert (2.5, "Q") in _actions(result)
    assert (3.0, EMPOWERED_AUTO_ATTACK) in _actions(result)
    # Q의 다음 쿨 복귀는 t=5.0 -> 5초 제한에 걸려 사용 안 함
    assert all(e.time < 5.0 for e in result.events)


def test_dps_combo_excludes_ultimate(kit, opponent):
    result = dps_combo(kit, 18, _stats(ability_haste=300), opponent, 18)
    assert result.count("R") == 0


def test_dps_combo_auto_count_scales_with_attack_speed(kit, opponent):
    result = dps_combo(kit, 18, _stats(attack_speed=2.0), opponent, 18)
    autos = result.count(AUTO_ATTACK) + result.count(EMPOWERED_AUTO_ATTACK)
    assert autos == 10


def test_burst_combo_runs_eight_hit_sequence(kit, opponent):
    result = burst_combo(kit, 18, _stats(), opponent, 18)

    assert [e.action for e in result.events] == [
        "E", EMPOWERED_AUTO_ATTACK,
        "Q", EMPOWERED_AUTO_ATTACK,
        "W", EMPOWERED_AUTO_ATTACK,
        "R", EMPOWERED_AUTO_ATTACK,
    ]
    assert result.total_damage == pytest.approx(sum(e.damage for e in result.events))
    assert result.dps is None


def test_burst_combo_skips_unlearned_ultimate(kit, opponent):
    # 레벨 5엔 R 미습득 -> R 없이 마지막 평타는 일반 평타
    result = burst_combo(kit, 5, _stats(), opponent, 5)
    assert result.count("R") == 0
    assert result.events[-1].action == AUTO_ATTACK


def test_passive_second_shot_adds_damage(kit, opponent):
    result = burst_combo(kit, 18, _stats(), opponent, 18)
    empowered = next(e for e in result.events if e.action == EMPOWERED_AUTO_ATTACK)
    armor = opponent.armor_at_level(18)
    assert empowered.damage == pytest.approx(100 * 1.60 * 100 / (100 + armor))


def test_crit_uses_expected_value_on_autos_but_not_on_r_shots(kit, opponent):
    stats = CombinedStats(
        attack_damage=100.0,
        bonus_attack_damage=0.0,
        attack_speed=1.0,
        crit_chance=0.4,
        life_steal_percent=0.0,
        ability_haste=0.0,
        crit_damage=2.3,
    )
    result = burst_combo(kit, 18, stats, opponent, 18)
    armor = opponent.armor_at_level(18)
    crit_factor = (1 - 0.4) + 2.3 * 0.4

    empowered = next(e for e in result.events if e.action == EMPOWERED_AUTO_ATTACK)
    assert empowered.damage == pytest.approx(100 * 1.60 * crit_factor * 100 / (100 + armor))

    # R: 치명타 배율 없이, 치명타 40% + 추가 치명타 피해량 30% -> 22 × (1 + 0.4 × 1.3) = 33.44 -> 33발
    r_event = next(e for e in result.events if e.action == "R")
    assert r_event.damage == pytest.approx((45 + 0.25 * 100) * 33 * 100 / (100 + armor))
