"""스킬/평타 조합에 따른 실제 데미지 계산 로직."""
from dataclasses import dataclass
from typing import Optional

from app.models.champion import ChampionStatsAtLevel
from app.models.item import ItemBuild
from app.models.opponent import Opponent
from app.models.rune import RunePage
from app.services.mitigation import damage_after_resist
from app.services.rune_effects import rune_stat_bonus

# 기본 치명타 피해량 200% (League of Legends 위키 스탯 표 기준).
# 무한의 대검을 끼면 추가 치명타 피해량 +30%p -> 230% (data/items.json의 crit_damage_bonus).
BASE_CRIT_DAMAGE = 2.0


@dataclass(frozen=True)
class CombinedStats:
    """챔피언 기본 스탯 + 아이템 + 상시 스탯 룬을 합산한 최종 전투 스탯.

    조건부 룬(집중 공격, 감전 등)은 콤보 계산 중에 반영된다 (services/rune_effects.py).
    """

    attack_damage: float
    bonus_attack_damage: float
    attack_speed: float
    crit_chance: float
    life_steal_percent: float
    ability_haste: float
    crit_damage: float = BASE_CRIT_DAMAGE  # 치명타 시 피해 배율 (2.0 = 200%)
    bonus_attack_speed: float = 0.0  # 아이템/룬으로 얻은 추가 공격속도 비율

    @property
    def base_attack_speed(self) -> float:
        """추가 공격속도를 제외한 레벨 기준 공격속도."""
        return self.attack_speed / (1 + self.bonus_attack_speed)

    @property
    def expected_crit_factor(self) -> float:
        """치명타 확률을 반영한 평균 피해 배율.

        매번 치명타를 랜덤으로 굴리지 않고 기댓값으로 계산:
          평균 = 일반 × (1 - 치명타확률) + 일반 × 치명타배율 × 치명타확률
               = 일반 × (1 + 치명타확률 × (치명타배율 - 1))
        """
        return 1 + self.crit_chance * (self.crit_damage - 1)


def combine_stats(
    champion_stats: ChampionStatsAtLevel,
    item_build: ItemBuild,
    rune_page: Optional[RunePage] = None,
) -> CombinedStats:
    items = item_build.total_stats()
    runes = rune_stat_bonus(rune_page, champion_stats.level, item_build)

    flat_ad = items.get("FlatPhysicalDamageMod", 0.0) + runes.attack_damage
    percent_as = items.get("PercentAttackSpeedMod", 0.0) + runes.attack_speed

    return CombinedStats(
        attack_damage=champion_stats.attack_damage + flat_ad,
        bonus_attack_damage=flat_ad,
        attack_speed=champion_stats.attack_speed * (1 + percent_as),
        crit_chance=min(items.get("FlatCritChanceMod", 0.0), 1.0),
        life_steal_percent=items.get("PercentLifeStealMod", 0.0) + runes.life_steal,
        ability_haste=items.get("AbilityHaste", 0.0) + runes.ability_haste,
        crit_damage=BASE_CRIT_DAMAGE + item_build.crit_damage_bonus(),
        bonus_attack_speed=percent_as,
    )


def expected_auto_attack_damage(
    stats: CombinedStats, opponent: Opponent, opponent_level: int
) -> float:
    """치명타 확률을 고려한 평타 1회 기대 데미지 (방어력 적용 후, 조건부 룬 미포함)."""
    armor = opponent.armor_at_level(opponent_level)
    raw_damage = stats.attack_damage * stats.expected_crit_factor
    return damage_after_resist(raw_damage, armor)


def auto_attack_dps(stats: CombinedStats, opponent: Opponent, opponent_level: int) -> float:
    """초당 평타 데미지 기댓값 (공격속도 반영, 조건부 룬 미포함)."""
    return expected_auto_attack_damage(stats, opponent, opponent_level) * stats.attack_speed
