"""루시안 스킬 콤보(DPS 콤보 / 폭딜 콤보) 데미지 계산.

단순화를 위한 가정:
- 스킬 시전 시간과 투사체 이동 시간은 0으로 처리.
- 평타는 t=0부터 공격속도 간격으로 꾸준히 발생 (E 돌진 등에 의한 평타 초기화, 선후딜 무시).
  공격속도가 콤보 도중 바뀌는 룬(치명적 속도, 칼날비)이 있으므로 다음 평타 시각은
  매 평타 직후의 공격속도로 계산.
- 스킬 랭크는 data/skills.json의 skill_order(표준 스킬 트리)로 루시안 레벨에서 자동 결정하며,
  아직 배우지 않은 스킬(랭크 0)은 콤보에서 건너뜀.
- 패시브(빛의 사도): 스킬 사용 후 다음 평타 1회가 2연발. 스킬을 연달아 여러 개 써도
  다음 평타 1회에만 적용(중첩 없음). 패시브 적중 시 E 쿨타임 감소 효과는 미반영.
- 치명타는 랜덤으로 굴리지 않고 기댓값으로 계산 (CombinedStats.expected_crit_factor):
  평타 1회 평균 = 일반 × (1 - 치명타확률) + 일반 × 치명타배율 × 치명타확률.
  치명타 배율은 기본 200%, 무한의 대검 보유 시 230%. 패시브 2번째 탄환도 치명타를
  별도로 판정하므로(위키) 같은 기댓값을 적용.
- R(빛의 심판)은 치명타 확률만큼 발사 수만 늘어나고(위키 V26.01 기준, Skill.hit_count 참고),
  탄환 피해에는 치명타 확률·치명타 피해량(무한의 대검 포함)을 적용하지 않음. Q/W도 치명타 없음.
- 스킬은 모든 타가 명중한다고 가정 (R의 모든 탄환 명중).
- AP는 0으로 가정해 AP 계수는 무시.
- 룬 효과와 관련 가정은 services/rune_effects.py 참고. 룬 발동 피해는 타임라인에 별도 행으로 표시.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.models.opponent import Opponent
from app.models.rune import RunePage
from app.models.skill import MAGIC, NO_DAMAGE, PHYSICAL, ChampionKit
from app.services.damage_calculator import CombinedStats
from app.services.mitigation import damage_after_resist
from app.services.rune_effects import RuneCombat, RuneProc

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


class _ComboSimulator:
    """평타/스킬을 하나씩 실행하며 피해(방어력/마저, 룬 효과 적용 후)와 쿨타임을 기록."""

    def __init__(
        self,
        kit: ChampionKit,
        level: int,
        stats: CombinedStats,
        opponent: Opponent,
        opponent_level: int,
        rune_page: Optional[RunePage],
        target_health_ratio: float,
        timed: bool,
    ):
        self.kit = kit
        self.stats = stats
        self.timed = timed
        self.ranks: Dict[str, int] = {key: kit.rank_at_level(key, level) for key in kit.skills}
        self.passive_ratio = kit.passive_second_shot_ratio(level)
        self.armor = opponent.armor_at_level(opponent_level)
        self.magic_resist = opponent.magic_resist_at_level(opponent_level)
        self.runes = RuneCombat(
            rune_page, level, stats, self.armor, self.magic_resist, target_health_ratio
        )
        self.events: List[ComboEvent] = []
        self.ready_at: Dict[str, float] = {}
        self.empowered = False

    def is_learned(self, key: str) -> bool:
        return self.ranks[key] > 0

    def attack_speed(self) -> float:
        bonus = self.stats.bonus_attack_speed + self.runes.bonus_attack_speed()
        return self.stats.base_attack_speed * (1 + bonus)

    def cast(self, key: str, t: float) -> None:
        self.runes.on_skill_cast(key, t)
        skill = self.kit.skills[key]
        damage = 0.0
        procs: List[RuneProc] = []
        if skill.damage_type != NO_DAMAGE:
            if skill.damage_type not in (PHYSICAL, MAGIC):
                raise ValueError(f"알 수 없는 피해 유형: {skill.damage_type}")
            self.runes.before_ability(t)
            conqueror_ad = self.runes.bonus_attack_damage()
            raw = skill.raw_damage(
                self.ranks[key],
                self.stats.attack_damage + conqueror_ad,
                self.stats.bonus_attack_damage + conqueror_ad,
                self.stats.crit_chance,
            )
            resist = self.armor if skill.damage_type == PHYSICAL else self.magic_resist
            damage = damage_after_resist(raw, resist) * self.runes.damage_multiplier(
                t, is_ultimate=key == "R"
            )
            procs = self.runes.after_ability(t)
        self._record(t, key, damage, procs)
        self.ready_at[key] = t + skill.cooldown_at(self.ranks[key], self.stats.ability_haste)
        self.empowered = True

    def attack(self, t: float) -> float:
        """평타 1회(패시브 적용 시 2연발)를 실행하고 다음 평타 시각을 반환."""
        shot_ratios = [1.0] + ([self.passive_ratio] if self.empowered else [])
        damage = 0.0
        procs: List[RuneProc] = []
        for ratio in shot_ratios:
            procs += self.runes.before_attack(t)
            ad = self.stats.attack_damage + self.runes.bonus_attack_damage()
            raw = ad * ratio * self.stats.expected_crit_factor
            damage += damage_after_resist(raw, self.armor) * self.runes.damage_multiplier(t)
            procs += self.runes.after_attack(t)
        action = EMPOWERED_AUTO_ATTACK if self.empowered else AUTO_ATTACK
        self._record(t, action, damage, procs)
        self.empowered = False
        return t + 1 / self.attack_speed()

    def _record(self, t: float, action: str, damage: float, procs: List[RuneProc]) -> None:
        shown_time = t if self.timed else None
        self.events.append(ComboEvent(shown_time, action, damage))
        # 한 행동에서 같은 룬이 여러 번 발동하면(예: 2연발 각각의 칼날비) 한 행으로 합산
        merged: Dict[str, float] = {}
        for proc in procs:
            merged[proc.name] = merged.get(proc.name, 0.0) + proc.damage
        for name, proc_damage in merged.items():
            self.events.append(ComboEvent(shown_time, name, proc_damage))

    def result(self, duration: Optional[float] = None) -> ComboResult:
        return ComboResult(
            events=tuple(self.events),
            total_damage=sum(e.damage for e in self.events),
            duration=duration,
        )


def dps_combo(
    kit: ChampionKit,
    level: int,
    stats: CombinedStats,
    opponent: Opponent,
    opponent_level: int,
    rune_page: Optional[RunePage] = None,
    target_health_ratio: float = 1.0,
    duration: float = DPS_COMBO_DURATION,
) -> ComboResult:
    """E → 평타 → Q → 평타 → W → 평타 이후, duration초까지 평타를 치며 쿨이 돌아온 스킬을 즉시 사용.

    duration초 "미만" 시점에 발생한 평타/스킬만 포함 (공속 1.0, 5초 → 평타 t=0,1,2,3,4 총 5회).
    같은 시각에 스킬 쿨타임과 평타가 겹치면 스킬을 먼저 사용해 그 평타에 패시브가 적용되도록 함.
    """
    sim = _ComboSimulator(
        kit, level, stats, opponent, opponent_level, rune_page, target_health_ratio, timed=True
    )

    # 시작 순서: 스킬은 직전 평타와 같은 시각에 시전(시전 시간 0), 이어서 다음 평타
    next_auto = 0.0
    last_auto = 0.0
    for key in DPS_OPENER:
        if next_auto >= duration:
            break
        if sim.is_learned(key):
            sim.cast(key, last_auto)
        last_auto = next_auto
        next_auto = sim.attack(next_auto)

    # 이후: 평타를 계속 치되, 쿨타임이 돌아온 스킬은 그 시각에 즉시 사용
    while True:
        pending = [(t, key) for key, t in sim.ready_at.items() if key in DPS_OPENER]
        next_skill_time, next_skill = min(pending) if pending else (float("inf"), None)

        if next_skill is not None and next_skill_time <= next_auto and next_skill_time < duration:
            sim.cast(next_skill, next_skill_time)
        elif next_auto < duration:
            next_auto = sim.attack(next_auto)
        else:
            break

    return sim.result(duration)


def burst_combo(
    kit: ChampionKit,
    level: int,
    stats: CombinedStats,
    opponent: Opponent,
    opponent_level: int,
    rune_page: Optional[RunePage] = None,
    target_health_ratio: float = 1.0,
) -> ComboResult:
    """E → 평타 → Q → 평타 → W → 평타 → R → 평타 8타 시퀀스 1회의 총 데미지 (시간 제한 없음).

    시간 개념이 없으므로 룬 판정용으로는 모든 행동이 t=0에 일어난다고 봄 (rune_effects 가정 참고).
    """
    sim = _ComboSimulator(
        kit, level, stats, opponent, opponent_level, rune_page, target_health_ratio, timed=False
    )
    for key in BURST_SEQUENCE:
        if sim.is_learned(key):
            sim.cast(key, 0.0)
        sim.attack(0.0)
    return sim.result()
