"""스킬/평타 조합에 따른 실제 데미지 계산 로직."""
from dataclasses import dataclass
from typing import Dict, Iterable

from app.models.champion import ChampionStatsAtLevel
from app.models.item import ItemBuild
from app.models.opponent import Opponent
from app.models.rune import Rune

# 기본 치명타 피해량 200% (League of Legends 위키 스탯 표 기준).
# 무한의 대검을 끼면 추가 치명타 피해량 +30%p -> 230% (data/items.json의 crit_damage_bonus).
BASE_CRIT_DAMAGE = 2.0


@dataclass(frozen=True)
class CombinedStats:
    """챔피언 기본 스탯 + 아이템 + 룬(고정 수치)을 합산한 최종 전투 스탯."""

    attack_damage: float
    bonus_attack_damage: float
    attack_speed: float
    crit_chance: float
    life_steal_percent: float
    ability_haste: float
    crit_damage: float = BASE_CRIT_DAMAGE  # 치명타 시 피해 배율 (2.0 = 200%)

    @property
    def expected_crit_factor(self) -> float:
        """치명타 확률을 반영한 평균 피해 배율.

        매번 치명타를 랜덤으로 굴리지 않고 기댓값으로 계산:
          평균 = 일반 × (1 - 치명타확률) + 일반 × 치명타배율 × 치명타확률
               = 일반 × (1 + 치명타확률 × (치명타배율 - 1))
        """
        return 1 + self.crit_chance * (self.crit_damage - 1)


def _rune_flat_stats(runes: Iterable[Rune]) -> Dict[str, float]:
    """고정 수치(flat_stat) 룬만 합산. 조건부 룬은 damage_calculator에서 아직 미반영."""
    totals: Dict[str, float] = {}
    for rune in runes:
        if rune.is_conditional:
            continue
        for stat, value in rune.stats.items():
            totals[stat] = totals.get(stat, 0.0) + value
    return totals


def combine_stats(
    champion_stats: ChampionStatsAtLevel,
    item_build: ItemBuild,
    runes: Iterable[Rune] = (),
) -> CombinedStats:
    item_totals = item_build.total_stats()
    rune_totals = _rune_flat_stats(runes)

    flat_ad = item_totals.get("FlatPhysicalDamageMod", 0.0) + rune_totals.get(
        "FlatPhysicalDamageMod", 0.0
    )
    percent_as = item_totals.get("PercentAttackSpeedMod", 0.0) + rune_totals.get(
        "PercentAttackSpeedMod", 0.0
    )
    crit_chance = item_totals.get("FlatCritChanceMod", 0.0) + rune_totals.get(
        "FlatCritChanceMod", 0.0
    )
    life_steal = item_totals.get("PercentLifeStealMod", 0.0) + rune_totals.get(
        "PercentLifeStealMod", 0.0
    )
    ability_haste = item_totals.get("AbilityHaste", 0.0) + rune_totals.get(
        "AbilityHaste", 0.0
    )

    return CombinedStats(
        attack_damage=champion_stats.attack_damage + flat_ad,
        bonus_attack_damage=flat_ad,
        attack_speed=champion_stats.attack_speed * (1 + percent_as),
        crit_chance=min(crit_chance, 1.0),
        life_steal_percent=life_steal,
        ability_haste=ability_haste,
        crit_damage=BASE_CRIT_DAMAGE + item_build.crit_damage_bonus(),
    )


def damage_after_resist(raw_damage: float, resist: float) -> float:
    """방어력/마법저항력 감소 공식 (둘 다 동일). 음수 저항(관통 등)도 라이엇 공식대로 처리."""
    if resist >= 0:
        mitigation = 100 / (100 + resist)
    else:
        mitigation = 2 - 100 / (100 - resist)
    return raw_damage * mitigation


def expected_auto_attack_damage(
    stats: CombinedStats, opponent: Opponent, opponent_level: int
) -> float:
    """치명타 확률을 고려한 평타 1회 기대 데미지 (방어력 적용 후)."""
    armor = opponent.armor_at_level(opponent_level)
    raw_damage = stats.attack_damage * stats.expected_crit_factor
    return damage_after_resist(raw_damage, armor)


def auto_attack_dps(stats: CombinedStats, opponent: Opponent, opponent_level: int) -> float:
    """초당 평타 데미지 기댓값 (공격속도 반영)."""
    return expected_auto_attack_damage(stats, opponent, opponent_level) * stats.attack_speed
