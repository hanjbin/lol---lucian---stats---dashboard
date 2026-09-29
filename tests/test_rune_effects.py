import pytest

from app.models.item import Item, ItemBuild
from app.models.opponent import Opponent
from app.models.rune import RuneTree
from app.models.skill import ChampionKit
from app.services.combo_calculator import AUTO_ATTACK, EMPOWERED_AUTO_ATTACK, burst_combo, dps_combo
from app.services.damage_calculator import CombinedStats
from app.services.rune_effects import level_scaled, rune_stat_bonus
from tests.test_rune import make_page

LEVEL = 18
NO_EFFECT_SECONDARY = ("Inspiration", ["MagicalFootwear", "BiscuitDelivery"])


@pytest.fixture
def trees():
    return RuneTree.load_all()


@pytest.fixture
def kit():
    return ChampionKit.load()


@pytest.fixture
def opponent():
    return Opponent.load_by_id("generic_squishy")


@pytest.fixture
def armor_factor(opponent):
    return 100 / (100 + opponent.armor_at_level(LEVEL))


@pytest.fixture
def mr_factor(opponent):
    return 100 / (100 + opponent.magic_resist_at_level(LEVEL))


def _stats():
    return CombinedStats(
        attack_damage=100.0,
        bonus_attack_damage=0.0,
        attack_speed=1.0,
        crit_chance=0.0,
        life_steal_percent=0.0,
        ability_haste=0.0,
    )


def _precision(trees, keystone, secondary=NO_EFFECT_SECONDARY):
    # 슬롯 룬은 데미지 영향 없는 조합 (최후의 일격은 상대 체력 100%면 미발동)
    return make_page(
        trees, "Precision", keystone, ["Triumph", "LegendHaste", "CoupDeGrace"], *secondary
    )


def _domination(trees, keystone):
    return make_page(
        trees, "Domination", keystone, ["TasteOfBlood", "SixthSense", "TreasureHunter"],
        *NO_EFFECT_SECONDARY,
    )


def _event(result, action):
    matches = [e for e in result.events if e.action == action]
    assert len(matches) == 1, f"{action}: {len(matches)}회"
    return matches[0]


def _autos(result):
    return [e for e in result.events if e.action in (AUTO_ATTACK, EMPOWERED_AUTO_ATTACK)]


# --- 공통 ------------------------------------------------------------------------------


def test_level_scaled_interpolates_linearly():
    assert level_scaled([40, 160], 1) == 40
    assert level_scaled([40, 160], 18) == 160
    assert level_scaled([40, 160], 10) == pytest.approx(40 + 120 * 9 / 17)


def test_page_with_only_no_effect_runes_matches_no_runes(trees, kit, opponent):
    page = _precision(trees, "FleetFootwork")
    for combo in (dps_combo, burst_combo):
        base = combo(kit, LEVEL, _stats(), opponent, LEVEL)
        with_runes = combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=page)
        assert with_runes.total_damage == pytest.approx(base.total_damage)


# --- 상시 스탯 룬 -------------------------------------------------------------------------


def test_legend_runes_at_max_stacks(trees):
    build = ItemBuild()
    alacrity = make_page(trees, "Precision", "FleetFootwork", ["Triumph", "LegendAlacrity", "CutDown"], *NO_EFFECT_SECONDARY)
    haste = make_page(trees, "Precision", "FleetFootwork", ["Triumph", "LegendHaste", "CutDown"], *NO_EFFECT_SECONDARY)
    bloodline = make_page(trees, "Precision", "FleetFootwork", ["Triumph", "LegendBloodline", "CutDown"], *NO_EFFECT_SECONDARY)

    assert rune_stat_bonus(alacrity, LEVEL, build).attack_speed == pytest.approx(0.18)
    assert rune_stat_bonus(haste, LEVEL, build).ability_haste == pytest.approx(15)
    assert rune_stat_bonus(bloodline, LEVEL, build).life_steal == pytest.approx(0.0675)


def test_sorcery_stat_runes_scale_with_level(trees):
    transcendence = make_page(trees, "Sorcery", "PhaseRush", ["ManaflowBand", "Transcendence", "Waterwalking"], *NO_EFFECT_SECONDARY)
    focus = make_page(trees, "Sorcery", "PhaseRush", ["ManaflowBand", "AbsoluteFocus", "Waterwalking"], *NO_EFFECT_SECONDARY)
    build = ItemBuild()

    assert [rune_stat_bonus(transcendence, lv, build).ability_haste for lv in (4, 5, 8)] == [0, 5, 10]
    assert rune_stat_bonus(focus, 1, build).attack_damage == pytest.approx(1.8)
    assert rune_stat_bonus(focus, 18, build).attack_damage == pytest.approx(18)


def test_jack_of_all_trades_counts_distinct_item_stats(trees):
    page = make_page(trees, "Precision", "FleetFootwork", ["Triumph", "LegendHaste", "CutDown"],
                     "Inspiration", ["MagicalFootwear", "JackOfAllTrades"])
    items = Item.load_all()
    build = ItemBuild()
    for item_id in ("3031", "6672", "3072"):  # 공격력/치명타, 공격력/공속, 공격력/치명타/생흡
        build.add(items[item_id])

    bonus = rune_stat_bonus(page, LEVEL, build)
    # 스탯 종류 4개 -> 스킬 가속 4 (-> 5종 미만이라 적응형 능력치 없음) + 전설: 가속 15
    assert bonus.ability_haste == pytest.approx(4 + 15)
    assert bonus.attack_damage == 0


# --- 조건부 룬 (콤보 중 발동) ------------------------------------------------------------


def test_press_the_attack_procs_on_third_shot_and_amplifies_after(trees, kit, opponent, armor_factor):
    base = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL)
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=_precision(trees, "PressTheAttack"))

    # 평타0(2연발) 2발 + 평타1 첫 발 = 3번째 탄환에서 발동 (t=1)
    proc = _event(result, "집중 공격")
    assert proc.time == 1.0
    assert proc.damage == pytest.approx(160 * armor_factor)
    # 발동 이후 행동(W, 평타2)은 8% 증폭
    assert _event(result, "W").damage == pytest.approx(_event(base, "W").damage * 1.08)
    assert _autos(result)[2].damage == pytest.approx(_autos(base)[2].damage * 1.08)
    assert _autos(result)[0].damage == pytest.approx(_autos(base)[0].damage)


def test_conqueror_stacks_raise_later_damage(trees, kit, opponent, armor_factor):
    result = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=_precision(trees, "Conqueror"))

    # Q 직전 스택 2 (원거리: 탄환당 1) -> 적응형 4.0 × 2 × 0.6 = 공격력 4.8
    bonus_ad = 2 * 4.0 * 0.6
    assert _event(result, "Q").damage == pytest.approx((205 + 1.20 * bonus_ad) * armor_factor)


def test_electrocute_procs_once_on_third_hit(trees, kit, opponent, armor_factor):
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=_domination(trees, "Electrocute"))

    # t=0: 평타(2발) + Q = 3회 적중 -> Q 바로 다음에 발동, 쿨다운 20초라 5초 안에 1회
    actions = [e.action for e in result.events]
    assert actions[actions.index("Q") + 1] == "감전"
    assert _event(result, "감전").damage == pytest.approx(240 * armor_factor)


def test_hail_of_blades_speeds_up_next_attacks(trees, kit, opponent):
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=_domination(trees, "HailOfBlades"))

    # 평타0(2발)이 3회 중 2회 소모 -> 공속 1.6으로 평타1은 0.625초 뒤,
    # 평타1 첫 발에서 마지막 1회 소모 -> 이후 원래 공속 1.0
    assert [e.time for e in _autos(result)[:3]] == pytest.approx([0.0, 0.625, 1.625])
    hail = [e for e in result.events if e.action == "칼날비"]
    assert [(e.time, e.damage) for e in hail] == [(0.0, pytest.approx(40)), (0.625, pytest.approx(20))]


def test_lethal_tempo_stacks_attack_speed_and_procs_at_max(trees, kit, opponent, armor_factor):
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=_precision(trees, "LethalTempo"))

    t1 = 1 / 1.08  # 2스택
    t2 = t1 + 1 / 1.16  # 4스택
    assert [e.time for e in _autos(result)[:3]] == pytest.approx([0.0, t1, t2])
    # 평타2 두 번째 탄환에서 6스택 -> 최대 스택 추가 피해 24 × (1 + 추가 공속 24%)
    first = next(e for e in result.events if e.action == "치명적 속도")
    assert first.time == pytest.approx(t2)
    assert first.damage == pytest.approx(24 * 1.24 * armor_factor)


def test_sudden_impact_after_e_dash(trees, kit, opponent):
    page = _precision(trees, "FleetFootwork", secondary=("Domination", ["SuddenImpact", "TreasureHunter"]))
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=page)

    proc = _event(result, "돌발 일격")  # 쿨다운 10초라 5초 안에 1회
    assert proc.time == 0.0
    assert proc.damage == pytest.approx(80)  # 고정 피해


def test_first_strike_amplifies_first_three_seconds(trees, kit, opponent):
    page = make_page(trees, "Inspiration", "FirstStrike", ["MagicalFootwear", "BiscuitDelivery", "CosmicInsight"],
                     "Precision", ["Triumph", "LegendHaste"])
    base = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL)
    result = dps_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=page)

    for b, r in zip(base.events, result.events):
        expected = b.damage * (1.07 if b.time < 3.0 else 1.0)
        assert r.damage == pytest.approx(expected)


@pytest.mark.parametrize(
    "rune, health, amplified",
    [("CoupDeGrace", 0.3, True), ("CoupDeGrace", 1.0, False), ("CutDown", 1.0, True), ("CutDown", 0.5, False)],
)
def test_health_threshold_runes(trees, kit, opponent, rune, health, amplified):
    page = make_page(trees, "Precision", "FleetFootwork", ["Triumph", "LegendHaste", rune], *NO_EFFECT_SECONDARY)
    base = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL)
    result = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=page, target_health_ratio=health)
    assert result.total_damage == pytest.approx(base.total_damage * (1.08 if amplified else 1.0))


def test_sorcery_comet_scorch_and_axiom(trees, kit, opponent, armor_factor, mr_factor):
    page = make_page(trees, "Sorcery", "ArcaneComet", ["NullifyingOrb", "Transcendence", "Scorch"], *NO_EFFECT_SECONDARY)
    base = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL)
    result = burst_combo(kit, LEVEL, _stats(), opponent, LEVEL, rune_page=page)

    # 첫 스킬 적중(Q)에서 1회씩 (폭딜 콤보는 한순간이라 쿨다운 동안 재발동 없음)
    assert _event(result, "신비로운 유성").damage == pytest.approx(100 * armor_factor)
    assert _event(result, "주문 작열").damage == pytest.approx(40 * mr_factor)
    assert _event(result, "R").damage == pytest.approx(_event(base, "R").damage * 1.12)
    assert _event(result, "Q").damage == pytest.approx(_event(base, "Q").damage)
