"""루시안 스킬 콤보(DPS 콤보 / 폭딜 콤보) 데미지 계산.

단순화를 위한 가정:
- 스킬 시전 시간과 투사체 이동 시간은 0으로 처리.
- 평타는 t=0부터 1/공격속도 간격으로 꾸준히 발생 (E 돌진 등에 의한 평타 초기화, 선후딜 무시).
- 스킬 랭크는 data/skills.json의 skill_order(표준 스킬 트리)로 루시안 레벨에서 자동 결정하며,
  아직 배우지 않은 스킬(랭크 0)은 콤보에서 건너뜀.
- 패시브(빛의 사도): 스킬 사용 후 다음 평타 1회가 2연발. 스킬을 연달아 여러 개 써도
  다음 평타 1회에만 적용(중첩 없음). 패시브 적중 시 E 쿨타임 감소 효과는 미반영.
- 평타(패시브 2번째 탄환 포함)는 치명타 확률 기댓값을 적용하고, 스킬은 치명타가 없다고 가정.
- 스킬은 모든 타가 명중한다고 가정 (R의 모든 탄환 명중, 치명타 확률에 따른 R 추가 탄환 미반영).
- AP는 0으로 가정해 AP 계수는 무시.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.models.opponent import Opponent
from app.models.skill import MAGIC, NO_DAMAGE, PHYSICAL, ChampionKit
from app.services.damage_calculator import DEFAULT_CRIT_MULTIPLIER, CombinedStats, damage_after_resist

DPS_COMBO_DURATION = 5.0
# DPS 콤보 시작 순서: 각 스킬 사용 후 평타 1회 (E → 평타 → Q → 평타 → W → 평타). R은 사용하지 않음.
DPS_OPENER: Tuple[str, ...] = ("E", "Q", "W")
# 폭딜 콤보: E → 평타 → Q → 평타 → W → 평타 → R → 평타, 시간 제한 없이 1회 실행.
BURST_SEQUENCE: Tuple[str, ...] = ("E", "Q", "W", "R")

AUTO_ATTACK = "평타"
EMPOWERED_AUTO_ATTACK = "평타 (패시브 2연발)"


@dataclass(frozen=True)
class ComboEvent:
    time: Optional[float]  # 폭딜 콤보는 시간 개념이 없으므로 None
    action: str
    damage: float


@dataclass(frozen=True)
class ComboResult:
    events: Tuple[ComboEvent, ...]
    total_damage: float
    duration: Optional[float] = None

    @property
    def dps(self) -> Optional[float]:
        if not self.duration:
            return None
        return self.total_damage / self.duration

    def count(self, action: str) -> int:
        return sum(1 for e in self.events if e.action == action)


class _ComboDamageModel:
    """콤보 한 타 한 타의 피해량(방어력/마저 적용 후)과 쿨타임을 계산."""

    def __init__(
        self,
        kit: ChampionKit,
        level: int,
        stats: CombinedStats,
        opponent: Opponent,
        opponent_level: int,
    ):
        self.kit = kit
        self.stats = stats
        self.ranks: Dict[str, int] = {key: kit.rank_at_level(key, level) for key in kit.skills}
        self.passive_ratio = kit.passive_second_shot_ratio(level)
        self.armor = opponent.armor_at_level(opponent_level)
        self.magic_resist = opponent.magic_resist_at_level(opponent_level)
        self.crit_multiplier = 1 + stats.crit_chance * (DEFAULT_CRIT_MULTIPLIER - 1)

    def is_learned(self, key: str) -> bool:
        return self.ranks[key] > 0

    def auto_attack(self, empowered: bool) -> float:
        raw = self.stats.attack_damage
        if empowered:
            raw += self.stats.attack_damage * self.passive_ratio
        return damage_after_resist(raw * self.crit_multiplier, self.armor)

    def skill(self, key: str) -> float:
        skill = self.kit.skills[key]
        if skill.damage_type == NO_DAMAGE:
            return 0.0
        raw = skill.raw_damage(
            self.ranks[key], self.stats.attack_damage, self.stats.bonus_attack_damage
        )
        if skill.damage_type == PHYSICAL:
            return damage_after_resist(raw, self.armor)
        if skill.damage_type == MAGIC:
            return damage_after_resist(raw, self.magic_resist)
        raise ValueError(f"알 수 없는 피해 유형: {skill.damage_type}")

    def cooldown(self, key: str) -> float:
        return self.kit.skills[key].cooldown_at(self.ranks[key], self.stats.ability_haste)


def dps_combo(
    kit: ChampionKit,
    level: int,
    stats: CombinedStats,
    opponent: Opponent,
    opponent_level: int,
    duration: float = DPS_COMBO_DURATION,
) -> ComboResult:
    """E → 평타 → Q → 평타 → W → 평타 이후, duration초까지 평타를 치며 쿨이 돌아온 스킬을 즉시 사용.

    duration초 "미만" 시점에 발생한 평타/스킬만 포함 (공속 1.0, 5초 → 평타 t=0,1,2,3,4 총 5회).
    같은 시각에 스킬 쿨타임과 평타가 겹치면 스킬을 먼저 사용해 그 평타에 패시브가 적용되도록 함.
    """
    model = _ComboDamageModel(kit, level, stats, opponent, opponent_level)
    interval = 1 / stats.attack_speed
    events: List[ComboEvent] = []
    ready_at: Dict[str, float] = {}
    auto_index = 0
    empowered = False

    def cast(key: str, t: float) -> None:
        nonlocal empowered
        events.append(ComboEvent(t, key, model.skill(key)))
        ready_at[key] = t + model.cooldown(key)
        empowered = True

    def attack(t: float) -> None:
        nonlocal empowered, auto_index
        action = EMPOWERED_AUTO_ATTACK if empowered else AUTO_ATTACK
        events.append(ComboEvent(t, action, model.auto_attack(empowered)))
        empowered = False
        auto_index += 1

    # 시작 순서: 스킬은 직전 평타와 같은 시각에 시전(시전 시간 0), 이어서 다음 평타
    last_auto_time = 0.0
    for key in DPS_OPENER:
        next_auto = auto_index * interval
        if next_auto >= duration:
            break
        if model.is_learned(key):
            cast(key, last_auto_time)
        attack(next_auto)
        last_auto_time = next_auto

    # 이후: 평타를 계속 치되, 쿨타임이 돌아온 스킬은 그 시각에 즉시 사용
    while True:
        next_auto = auto_index * interval
        pending = [(ready_at[key], key) for key in DPS_OPENER if key in ready_at]
        next_skill_time, next_skill = min(pending) if pending else (float("inf"), None)

        if next_skill is not None and next_skill_time <= next_auto and next_skill_time < duration:
            cast(next_skill, next_skill_time)
        elif next_auto < duration:
            attack(next_auto)
        else:
            break

    return ComboResult(
        events=tuple(events),
        total_damage=sum(e.damage for e in events),
        duration=duration,
    )


def burst_combo(
    kit: ChampionKit,
    level: int,
    stats: CombinedStats,
    opponent: Opponent,
    opponent_level: int,
) -> ComboResult:
    """E → 평타 → Q → 평타 → W → 평타 → R → 평타 8타 시퀀스 1회의 총 데미지 (시간 제한 없음)."""
    model = _ComboDamageModel(kit, level, stats, opponent, opponent_level)
    events: List[ComboEvent] = []

    for key in BURST_SEQUENCE:
        learned = model.is_learned(key)
        if learned:
            events.append(ComboEvent(None, key, model.skill(key)))
        action = EMPOWERED_AUTO_ATTACK if learned else AUTO_ATTACK
        events.append(ComboEvent(None, action, model.auto_attack(learned)))

    return ComboResult(events=tuple(events), total_damage=sum(e.damage for e in events))
