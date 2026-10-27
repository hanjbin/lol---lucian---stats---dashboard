import pytest

from app.models.item import Item, ItemBuild
from app.models.opponent import Opponent
from app.models.rune import RuneTree
from app.models.skill import ChampionKit
from app.services.combo_calculator import burst_combo, dps_combo
from app.services.damage_calculator import CombinedStats
from tests.test_rune import make_page

LEVEL = 18


@pytest.fixture
def kit():
    return ChampionKit.load()


@pytest.fixture
def opponent():
    return Opponent.load_by_id("generic_squishy")


@pytest.fixture
def armor_factor(opponent):
    return 100 / (100 + opponent.armor_at_level(LEVEL))


def _stats(ability_haste=0.0):
    # 기본 공격력 100 (추가 공격력 0), 공속 1.0 -> 평타 t=0,1,2,3,4
    return CombinedStats(
        attack_damage=100.0,
        bonus_attack_damage=0.0,
        attack_speed=1.0,
        crit_chance=0.0,
        life_steal_percent=0.0,
        ability_haste=ability_haste,
    )


def _build(*item_ids):
    items = Item.load_all()
    build = ItemBuild()
    for item_id in item_ids:
        build.add(items[item_id])
    return build


def _procs(result, name):
    return [(e.time, e.damage) for e in result.events if e.action == name]


def test_opponent_health_grows_with_level(opponent):
    assert opponent.health_at_level(1) == 630
    assert opponent.health_at_level(18) == pytest.approx(630 + 105 * 17)


def test_items_without_combo_passive_do_not_change_combos(kit, opponent):
    base = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL)
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("3031", "3072", "3085"))
    assert result.total_damage == pytest.approx(base.total_damage)


def test_kraken_slayer_procs_every_third_shot(kit, opponent, armor_factor):
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("6672"))

    # 탄환: t0(2발) t1(2발) t2(2발) t3(1발) t4(1발) -> 3번째(t1), 6번째(t2) 탄환에서 발동
    assert _procs(result, "크라켄 학살자") == [
        (1.0, pytest.approx(168 * armor_factor)),
        (2.0, pytest.approx(168 * armor_factor)),
    ]


def test_kraken_slayer_scales_with_target_missing_health(kit, opponent, armor_factor):
    result = burst_combo(
        kit, LEVEL, _stats(), opponent, LEVEL, target_health_ratio=0.2, item_build=_build("6672")
    )
    # 잃은 체력 80% -> 0.75 × 0.8 = 60% 증가
    damage = _procs(result, "크라켄 학살자")[0][1]
    assert damage == pytest.approx(168 * 1.6 * armor_factor)


def test_spellblade_triggers_after_skill_with_cooldown(kit, opponent, armor_factor):
    # 기본 쿨타임: E(t=0)로 충전 -> 평타0 첫 탄환에서 발동, 1.5초 대기시간 중 Q(t=0)·W(t=1)는 충전 못 함
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("3078"))
    assert _procs(result, "주문검 (삼위일체)") == [(0.0, pytest.approx(200 * armor_factor))]

    # 스킬 가속 100 -> Q가 t=2.5에 다시 사용돼 주문검 충전, t=3 평타에서 한 번 더 발동
    hasted = dps_combo(kit, LEVEL, _stats(ability_haste=100), opponent, LEVEL, item_build=_build("3078"))
    assert [t for t, _ in _procs(hasted, "주문검 (삼위일체)")] == [0.0, 3.0]


def test_spellblade_once_in_burst_combo(kit, opponent):
    result = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("3078"))
    assert len(_procs(result, "주문검 (삼위일체)")) == 1


def test_hullbreaker_procs_on_fifth_shot(kit, opponent, armor_factor):
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("3181"))

    # 5번째 탄환 = t2 평타의 첫 발. 기본 공격력 84% + 대상 최대 체력 3.5%
    raw = 0.84 * 100 + 0.035 * opponent.health_at_level(LEVEL)
    assert _procs(result, "선체파괴자") == [(2.0, pytest.approx(raw * armor_factor))]


def test_item_procs_are_amplified_by_press_the_attack_after_it_procs(kit, opponent, armor_factor):
    page = make_page(
        RuneTree.load_all(), "Precision", "PressTheAttack", ["Triumph", "LegendHaste", "CoupDeGrace"],
        "Inspiration", ["MagicalFootwear", "BiscuitDelivery"],
    )
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=page, item_build=_build("6672"))

    # 크라켄(t1)은 집중 공격과 같은 탄환에서 발동 -> 집중 공격 발동 전이라 증폭 없음, t2는 8% 증폭
    assert _procs(result, "크라켄 학살자") == [
        (1.0, pytest.approx(168 * armor_factor)),
        (2.0, pytest.approx(168 * 1.08 * armor_factor)),
    ]


# ---------------------------------------------------------------------------
# 치명타 아이템 고유 효과
# ---------------------------------------------------------------------------
from dataclasses import replace  # noqa: E402

from app.models.champion import Champion  # noqa: E402
from app.services.damage_calculator import combine_stats, expected_auto_attack_damage  # noqa: E402
from app.services.mitigation import effective_armor  # noqa: E402


def _crit_stats(crit_chance):
    return replace(_stats(), crit_chance=crit_chance)


def test_effective_armor_applies_percent_then_flat_and_never_below_zero():
    assert effective_armor(100, 0.35, 10) == pytest.approx(55)
    assert effective_armor(5, 0.0, 10) == 0
    assert effective_armor(-10, 0.35, 10) == -10  # 관통은 음수 방어력에 효과 없음


def test_combine_stats_reads_armor_pen_and_lethality_from_items():
    stats = combine_stats(Champion.load("Lucian").stats_at_level(LEVEL), _build("3036", "6676"))
    assert stats.armor_pen_percent == 0.35
    assert stats.lethality == 10


def test_armor_pen_raises_auto_attack_damage(opponent):
    armor = opponent.armor_at_level(LEVEL)
    pen = replace(_stats(), armor_pen_percent=0.35, lethality=10)
    expected = 100 * 100 / (100 + armor * 0.65 - 10)
    assert expected_auto_attack_damage(pen, opponent, LEVEL) == pytest.approx(expected)


@pytest.mark.parametrize("pair", [("3078", "3508"), ("3036", "3033")])
def test_same_unique_group_items_cannot_be_combined(pair):
    with pytest.raises(ValueError):
        _build(*pair)


def test_energized_items_proc_once_on_first_attack_as_magic_damage(kit, opponent):
    mr_factor = 100 / (100 + opponent.magic_resist_at_level(LEVEL))
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("3095", "3094"))
    assert _procs(result, "스톰레이저 (충전 공격)") == [(0.0, pytest.approx(100 * mr_factor))]
    assert _procs(result, "래피드파이어 대포 (충전 공격)") == [(0.0, pytest.approx(40 * mr_factor))]


def test_essence_reaver_spellblade_scales_with_crit_chance(kit, opponent, armor_factor):
    result = burst_combo(kit, LEVEL, _crit_stats(0.5), opponent, LEVEL, item_build=_build("3508"))
    # 기본 공격력 125% + 치명타 확률 50% × 50% = 150%
    assert _procs(result, "주문검 (정수 약탈자)") == [(None, pytest.approx(150 * armor_factor))]


def test_navori_reduces_remaining_basic_ability_cooldowns(kit, opponent):
    def casts(result):
        return [e.time for e in result.events if e.action in ("Q", "W", "E")]

    base = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL)
    navori = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("6675"))
    assert len(casts(navori)) > len(casts(base))
    assert navori.total_damage > base.total_damage


def test_fiendhunter_empowers_attacks_after_ultimate(kit, opponent, armor_factor):
    base = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL)
    bolts = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("2512"))
    # R 이후 마지막 평타(2연발)만 강화: 치명타 0%면 강제 치명타 60% 추가 피해
    assert bolts.events[-1].damage == pytest.approx(base.events[-1].damage * 1.6)
    assert bolts.events[1].damage == pytest.approx(base.events[1].damage)  # R 전 평타는 그대로

    crit = burst_combo(kit, LEVEL, _crit_stats(0.5), opponent, LEVEL, item_build=_build("2512"))
    true_damage = _procs(crit, "악마사냥꾼의 화살 (개시 사격) 고정 피해")
    # 탄환 2발(100% + 60%) × 치명타 확률 0.5 × 치명타 배율 2 × 15%
    assert true_damage == [(None, pytest.approx(100 * 1.6 * 0.5 * 2 * 0.15))]


def test_fiendhunter_does_nothing_without_ultimate(kit, opponent):
    base = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL)
    bolts = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("2512"))
    assert bolts.total_damage == pytest.approx(base.total_damage)


def test_hexoptics_amplifies_basic_attacks_only(kit, opponent):
    base = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL)
    hex_ = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("2523"))
    for b, h in zip(base.events, hex_.events):
        expected = 1.1 if b.action.startswith("평타") else 1.0
        assert h.damage == pytest.approx(b.damage * expected)


@pytest.mark.parametrize("bonus_health, amp", [(0, 1.0), (1000, 1.10), (3000, 1.15)])
def test_giant_slayer_scales_with_target_bonus_health(kit, opponent, bonus_health, amp):
    base = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("3036"))
    result = burst_combo(
        kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("3036"), target_bonus_health=bonus_health
    )
    assert result.total_damage == pytest.approx(base.total_damage * amp)


def test_collector_executes_when_target_left_below_five_percent(kit, opponent):
    max_health = opponent.health_at_level(LEVEL)
    total = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("6676")).total_damage

    # 콤보 후 최대 체력의 3%가 남도록 현재 체력 설정 -> 남은 체력만큼 처형
    ratio = (total + 0.03 * max_health) / max_health
    result = burst_combo(
        kit, LEVEL, _stats(), opponent, LEVEL, target_health_ratio=ratio, item_build=_build("6676")
    )
    assert _procs(result, "징수의 총 (처형)") == [(None, pytest.approx(0.03 * max_health))]
    assert result.total_damage == pytest.approx(ratio * max_health)


def test_collector_does_not_execute_healthy_target(kit, opponent):
    result = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL, item_build=_build("6676"))
    assert _procs(result, "징수의 총 (처형)") == []
