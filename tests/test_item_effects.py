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
