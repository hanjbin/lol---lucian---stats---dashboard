"""룬 효과 계산: 상시 스탯 룬(combine_stats에 반영) + 콤보 중 발동 조건을 판단하는 조건부 룬.

==========================================================================================
구현한 룬 목록과 선택 이유
==========================================================================================
구조/한글 이름/수치는 Data Dragon 16.19.1 runesReforged.json 기준 (data/runes.json).
트리마다 루시안이 실전에서 자주 쓰는 룬 위주로 골랐고, 모든 슬롯에 선택지가 1개 이상 있도록 함.
"채용률"은 일반적인 루시안 룬 채용 경향 기준이며, 특정 통계 사이트의 수치를 확인한 것은 아님.
효과 구분: stat = 상시 스탯, combo = 콤보 중 조건 판단, none = 데미지 계산과 무관(선택만 가능).

[정밀] 메인/보조
  키스톤
  - 집중 공격 (combo): 원딜 루시안의 대표 키스톤. 패시브 2연발 덕분에 평타 2번(3발)이면 바로 발동.
  - 치명적 속도 (combo): 공속/치명타 빌드 루시안이 선택. 스택마다 공속 증가 -> 평타 간격에 반영.
  - 정복자 (combo): 미드/탑 루시안의 대표 키스톤. 적중마다 쌓이는 공격력이 이후 피해에 반영.
  - 기민한 발놀림 (none): 라인전 유지력용으로 자주 쓰지만 회복/이동속도뿐이라 데미지 영향 없음.
  슬롯 1
  - 승전보, 침착 (none): 루시안이 가장 많이 쓰는 두 룬. 회복/마나 효과라 데미지 영향 없음.
  슬롯 2
  - 전설: 민첩함 (stat): 공격속도. 원딜 루시안의 기본 선택.
  - 전설: 가속 (stat): 스킬 가속. 스킬 위주 루시안이 선택.
  - 전설: 핏빛 길 (stat): 생명력 흡수 (최대 스택 시 체력 +85는 체력을 모델링하지 않아 제외).
  슬롯 3
  - 최후의 일격 / 체력차 극복 (combo): 루시안이 가장 많이 쓰는 두 룬. UI에서 입력한 상대 체력 비율이
    조건(40% 미만 / 60% 초과)을 만족하면 모든 피해 8% 증가.
  - 최후의 저항은 루시안 자신의 체력 변화를 모델링하지 않아 제외.

[지배] 메인/보조
  키스톤
  - 감전 (combo): 미드 루시안의 폭딜 키스톤. 3초 안에 공격/스킬 3회 적중 시 추가 피해.
  - 칼날비 (combo): 짧은 교전용. 공격 3회 동안 공속 증가(평타 간격에 반영) + 적중 시 고정 피해.
  - 어둠의 수확은 영혼 스택 누적과 상대 체력 50% 미만 조건이 필요해 제외.
  슬롯 1
  - 돌발 일격 (combo): 루시안 E(돌진) 직후 적중에 고정 피해. 보조 지배에서 가장 많이 쓰는 룬.
  - 피의 맛 (none): 회복뿐.
  - 비열한 한 방은 루시안에게 이동 방해 스킬이 없어 발동할 수 없으므로 제외.
  슬롯 2
  - 육감, 섬뜩한 기념품 (none): 이 슬롯은 모두 시야/장신구 효과뿐이라 대표 룬 2개만 포함.
  슬롯 3
  - 보물 사냥꾼 (none): 가장 많이 쓰는 룬. 골드 효과뿐.
  - 궁극의 사냥꾼 (none): 궁극기 쿨타임 감소지만 두 콤보 모두 R 쿨타임을 쓰지 않아 계산 영향 없음.

[마법] 메인 전용 (요구사항상 보조 선택지에서 제외)
  루시안이 마법을 메인으로 쓰는 경우는 드물어 트리를 구성할 수 있을 정도만 포함.
  키스톤
  - 신비로운 유성 (combo): 스킬 적중 시 추가 피해. 거리 비례 증폭(최대 750 거리에서 +100%)은 미반영.
  - 폭풍전사의 포효 (none): 이동속도뿐.
  슬롯 1
  - 액시옴 비전 마법사 (combo): 궁극기 피해 12% 증가 (루시안 R은 첫 적중 대상 단일 피해라 광역 8%가 아닌 12%).
  - 마나순환 팔찌 (none): 마나뿐.
  슬롯 2
  - 깨달음 (stat): 레벨 5/8에 스킬 가속 +5씩. 루시안이 마법 트리를 쓸 때의 단골 룬.
  - 절대 집중 (stat): 체력 70% 이상일 때 공격력. 루시안은 체력이 가득 찬 상태로 가정.
  슬롯 3
  - 주문 작열 (combo): 스킬 적중 시 추가 마법 피해.
  - 물 위를 걷는 자 (none): 강가에서만 발동 -> 강가 밖 교전을 가정해 효과 없음.
  - 폭풍의 결집은 게임 시간을 모델링하지 않아 제외.

[영감] 메인/보조
  키스톤
  - 선제공격 (combo): 교전 시작 3초간 피해 7% 증가. 루시안이 쓰는 영감 키스톤은 사실상 이것뿐이라 단독 포함.
  슬롯 1: 마법의 신발, 환급 (none) - 가장 많이 쓰는 두 룬. 이동속도/골드 효과뿐.
  슬롯 2: 비스킷 배달, 시간 왜곡 물약 (none) - 가장 많이 쓰는 두 룬. 회복 효과뿐.
  슬롯 3
  - 우주적 통찰력 (none): 소환사 주문/아이템 가속이라 스킬 쿨타임과 무관.
  - 다재다능 (stat): 아이템 스탯 종류당 스킬 가속 +1, 5/10종에서 적응형 능력치 +8/+20.
    도란 아이템/2티어 신발의 이동 속도·체력·모든 피해 흡혈 등도 스탯 종류로 셈 (data/items.json).

[결의] 트리는 요구사항 범위 밖이라 제외.

==========================================================================================
공통 가정
==========================================================================================
- 툴팁에 "a~b (레벨 비례)"로 표기된 수치는 루시안 레벨 1~18 사이 선형 보간 (Data Dragon에 보간 공식 없음).
- 적응형 능력치: 루시안은 AD 챔피언이므로 1 적응형 능력치 = 공격력 0.6, 적응형 피해 = 물리 피해.
- 루시안 체력은 가득 찬 상태로 가정 (절대 집중 항상 발동).
- 전설 룬 스택은 최대치로 가정 (중후반 교전 기준).
- 상대 체력은 콤보 도중 변하지 않고 UI에서 입력한 비율로 고정 (최후의 일격/체력차 극복 판정용).
- 패시브(빛의 사도) 2연발의 두 탄환은 각각 별개의 기본 공격으로 셈 (위키: 두 번째 탄환도 공격 시 효과 발동).
  -> 집중 공격 3타, 감전 3회, 치명적 속도/정복자 스택, 칼날비 공격 횟수를 탄환 단위로 계산.
- R은 여러 발이지만 룬 발동 판정(적중 횟수, 스택, 쿨다운)에서는 스킬 1회 적중으로 취급.
- 폭딜 콤보는 시간 개념이 없어 모든 행동이 한순간(t=0)에 일어난다고 봄
  -> 지속시간 조건은 항상 충족, 쿨다운이 있는 효과는 콤보당 1회만 발동.
- 룬으로 생긴 추가 피해에도 집중 공격/선제공격/최후의 일격/체력차 극복의 피해 증폭을 적용.
  단 집중 공격 발동 피해 자체에는 집중 공격 증폭을 적용하지 않음 (증폭은 발동 이후부터).
- 투사체/유성/주문 작열(1초 후 피해)의 지연 시간은 0으로 처리.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

from app.models._common import MAX_LEVEL, MIN_LEVEL
from app.models.item import ItemBuild
from app.models.rune import RunePage
from app.services.mitigation import damage_after_resist

if TYPE_CHECKING:
    from app.services.damage_calculator import CombinedStats

ADAPTIVE_FORCE_TO_AD = 0.6

PHYSICAL = "physical"
MAGIC = "magic"
TRUE_DAMAGE = "true"


def level_scaled(value_range: Sequence[float], level: int) -> float:
    """[레벨1 값, 레벨18 값]을 레벨에 따라 선형 보간."""
    low, high = value_range
    return low + (high - low) * (level - MIN_LEVEL) / (MAX_LEVEL - MIN_LEVEL)


# ---------------------------------------------------------------------------------------
# 상시 스탯 룬 (effect = "stat")
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RuneStatBonus:
    attack_damage: float = 0.0
    attack_speed: float = 0.0  # 추가 공격속도 비율 (0.18 = +18%)
    ability_haste: float = 0.0
    life_steal: float = 0.0


def rune_stat_bonus(page: Optional[RunePage], level: int, item_build: ItemBuild) -> RuneStatBonus:
    if page is None:
        return RuneStatBonus()

    ad = attack_speed = haste = life_steal = 0.0
    for rune in page.runes:
        p = rune.params
        if rune.key == "LegendAlacrity":
            attack_speed += p["base_attack_speed"] + p["attack_speed_per_stack"] * p["max_stacks"]
        elif rune.key == "LegendHaste":
            haste += p["ability_haste_per_stack"] * p["max_stacks"]
        elif rune.key == "LegendBloodline":
            life_steal += p["life_steal_per_stack"] * p["max_stacks"]
        elif rune.key == "Transcendence":
            haste += sum(h for min_level, h in p["ability_haste_by_level"] if level >= min_level)
        elif rune.key == "AbsoluteFocus":
            ad += level_scaled(p["attack_damage"], level)
        elif rune.key == "JackOfAllTrades":
            # 아이템에서 얻은 서로 다른 스탯 종류 수 = 스택. 위키 기준 이동 속도, 체력, 모든 피해 흡혈,
            # 강인함, 마법 관통력, 치명타 피해량 등도 포함 (적응형 능력치, 물리 흡혈, 둔화 저항은 제외).
            stat_types = {stat for item in item_build.items for stat, v in item.stats.items() if v}
            if item_build.crit_damage_bonus():
                stat_types.add("CritDamage")
            stacks = len(stat_types)
            haste += stacks * p["ability_haste_per_stack"]
            force = max((f for need, f in p["adaptive_force_by_stacks"] if stacks >= need), default=0)
            ad += force * ADAPTIVE_FORCE_TO_AD

    return RuneStatBonus(
        attack_damage=ad, attack_speed=attack_speed, ability_haste=haste, life_steal=life_steal
    )


# ---------------------------------------------------------------------------------------
# 콤보 중 조건부 룬 (effect = "combo")
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DamageProc:
    name: str
    damage: float  # 저항/증폭 적용 후 최종 피해


class RuneCombat:
    """콤보 1회 동안의 룬 상태(스택, 버프, 쿨다운)를 추적하며 발동 여부를 판단.

    콤보 시뮬레이터는 공격 탄환/스킬 적중마다 before_*/after_* 훅을 호출하고,
    피해 계산에 bonus_attack_damage / bonus_attack_speed / damage_multiplier를 사용한다.
    """

    def __init__(
        self,
        page: Optional[RunePage],
        level: int,
        stats: "CombinedStats",
        armor: float,
        magic_resist: float,
        target_health_ratio: float = 1.0,
    ):
        self.level = level
        self.stats = stats
        self.armor = armor
        self.magic_resist = magic_resist
        self.target_health_ratio = target_health_ratio
        self._params: Dict[str, dict] = {r.key: r.params for r in page.runes} if page else {}
        self._names: Dict[str, str] = {r.key: r.name for r in page.runes} if page else {}

        self._ready_at: Dict[str, float] = {}
        self._attack_streak = 0  # 집중 공격
        self._exposed = False  # 집중 공격 발동 후 피해 증폭
        self._tempo_stacks = 0  # 치명적 속도
        self._conqueror_stacks = 0
        self._electrocute_hits: List[float] = []
        self._hail_charges = 0  # 칼날비 남은 공격 횟수
        self._last_attack_time: Optional[float] = None
        self._dash_until: Optional[float] = None  # 돌발 일격
        self._first_strike_until: Optional[float] = None

    # --- 내부 유틸 ------------------------------------------------------------------

    def _p(self, key: str) -> Optional[dict]:
        return self._params.get(key)

    def _ready(self, key: str, t: float) -> bool:
        return t >= self._ready_at.get(key, float("-inf"))

    def _proc(self, key: str, raw: float, damage_type: str, t: float) -> DamageProc:
        if damage_type == PHYSICAL:
            raw = damage_after_resist(raw, self.armor)
        elif damage_type == MAGIC:
            raw = damage_after_resist(raw, self.magic_resist)
        return DamageProc(self._names[key], raw * self.damage_multiplier(t))

    def _start_combat(self, t: float) -> None:
        p = self._p("FirstStrike")
        if p and self._first_strike_until is None:
            self._first_strike_until = t + p["duration_seconds"]

    # --- 스탯/피해 보정 --------------------------------------------------------------

    def bonus_attack_damage(self) -> float:
        """정복자 스택으로 얻은 추가 공격력."""
        p = self._p("Conqueror")
        if not p:
            return 0.0
        per_stack = level_scaled(p["adaptive_force_per_stack"], self.level) * ADAPTIVE_FORCE_TO_AD
        return self._conqueror_stacks * per_stack

    def bonus_attack_speed(self) -> float:
        """치명적 속도 스택 / 칼날비로 얻은 추가 공격속도 비율."""
        bonus = 0.0
        p = self._p("LethalTempo")
        if p:
            bonus += self._tempo_stacks * p["attack_speed_per_stack"]
        p = self._p("HailOfBlades")
        if p and self._hail_charges > 0:
            bonus += p["attack_speed"]
        return bonus

    def damage_multiplier(self, t: float, is_ultimate: bool = False) -> float:
        multiplier = 1.0
        p = self._p("PressTheAttack")
        if p and self._exposed:
            multiplier *= 1 + p["damage_amp"]
        p = self._p("FirstStrike")
        if p and self._first_strike_until is not None and t < self._first_strike_until:
            multiplier *= 1 + p["damage_amp"]
        p = self._p("CoupDeGrace")
        if p and self.target_health_ratio < p["target_health_below"]:
            multiplier *= 1 + p["damage_amp"]
        p = self._p("CutDown")
        if p and self.target_health_ratio > p["target_health_above"]:
            multiplier *= 1 + p["damage_amp"]
        p = self._p("NullifyingOrb")
        if p and is_ultimate:
            multiplier *= 1 + p["ultimate_damage_amp"]
        return multiplier

    # --- 이벤트 훅 -------------------------------------------------------------------

    def on_skill_cast(self, skill_key: str, t: float) -> None:
        p = self._p("SuddenImpact")
        if p and skill_key == "E":
            self._dash_until = t + p["duration_seconds"]

    def before_attack(self, t: float) -> List[DamageProc]:
        """기본 공격 탄환 1발의 피해 직전: 공격 시 효과와 스택/버프 갱신."""
        self._start_combat(t)
        procs: List[DamageProc] = []

        p = self._p("LethalTempo")
        if p:
            self._tempo_stacks = min(self._tempo_stacks + 1, p["max_stacks"])
            if self._tempo_stacks == p["max_stacks"]:
                # 최대 스택일 때 공격 시 추가 적응형 피해, 추가 공속 1%당 1% 증가
                bonus_as = self.stats.bonus_attack_speed + self.bonus_attack_speed()
                raw = level_scaled(p["max_stack_damage"], self.level) * (1 + bonus_as)
                procs.append(self._proc("LethalTempo", raw, PHYSICAL, t))

        p = self._p("HailOfBlades")
        if p:
            gap_exceeded = (
                self._last_attack_time is not None
                and t - self._last_attack_time > p["max_gap_seconds"]
            )
            if gap_exceeded:
                self._hail_charges = 0
            if self._hail_charges == 0 and self._ready("HailOfBlades", t):
                self._hail_charges = p["attacks"]
                self._ready_at["HailOfBlades"] = t + p["cooldown"]
            if self._hail_charges > 0:
                # 이번 공격이 칼날비 공격 횟수를 1회 소모. 남은 횟수가 있어야 다음 평타 간격이 빨라짐.
                self._hail_charges -= 1
                raw = level_scaled(p["on_hit_true_damage"], self.level) + p["bonus_ad_ratio"] * (
                    self.stats.bonus_attack_damage + self.bonus_attack_damage()
                )
                procs.append(self._proc("HailOfBlades", raw, TRUE_DAMAGE, t))

        self._last_attack_time = t
        return procs

    def after_attack(self, t: float) -> List[DamageProc]:
        """기본 공격 탄환 1발 적중 후."""
        procs: List[DamageProc] = []
        p = self._p("PressTheAttack")
        if p and not self._exposed:
            self._attack_streak += 1
            if self._attack_streak >= p["attacks_required"]:
                raw = level_scaled(p["damage"], self.level)
                procs.append(self._proc("PressTheAttack", raw, PHYSICAL, t))
                self._exposed = True
        procs += self._after_any_hit(t)
        self._add_conqueror_stacks("stacks_per_attack")
        return procs

    def before_ability(self, t: float) -> None:
        self._start_combat(t)

    def after_ability(self, t: float) -> List[DamageProc]:
        """피해를 주는 스킬(Q/W/R) 적중 후."""
        procs = self._after_any_hit(t)
        bonus_ad = self.stats.bonus_attack_damage + self.bonus_attack_damage()

        p = self._p("ArcaneComet")
        if p and self._ready("ArcaneComet", t):
            raw = level_scaled(p["damage"], self.level) + p["bonus_ad_ratio"] * bonus_ad
            procs.append(self._proc("ArcaneComet", raw, PHYSICAL, t))
            self._ready_at["ArcaneComet"] = t + level_scaled(p["cooldown"], self.level)

        p = self._p("Scorch")
        if p and self._ready("Scorch", t):
            procs.append(self._proc("Scorch", level_scaled(p["magic_damage"], self.level), MAGIC, t))
            self._ready_at["Scorch"] = t + p["cooldown"]

        self._add_conqueror_stacks("stacks_per_ability")
        return procs

    def _after_any_hit(self, t: float) -> List[DamageProc]:
        procs: List[DamageProc] = []
        bonus_ad = self.stats.bonus_attack_damage + self.bonus_attack_damage()

        p = self._p("Electrocute")
        if p:
            self._electrocute_hits = [
                h for h in self._electrocute_hits if t - h < p["window_seconds"]
            ] + [t]
            if len(self._electrocute_hits) >= p["hits_required"] and self._ready("Electrocute", t):
                raw = level_scaled(p["damage"], self.level) + p["bonus_ad_ratio"] * bonus_ad
                procs.append(self._proc("Electrocute", raw, PHYSICAL, t))
                self._ready_at["Electrocute"] = t + p["cooldown"]
                self._electrocute_hits = []

        p = self._p("SuddenImpact")
        if p and self._dash_until is not None and t <= self._dash_until and self._ready("SuddenImpact", t):
            raw = level_scaled(p["true_damage"], self.level)
            procs.append(self._proc("SuddenImpact", raw, TRUE_DAMAGE, t))
            self._ready_at["SuddenImpact"] = t + p["cooldown"]
            self._dash_until = None

        return procs

    def _add_conqueror_stacks(self, stack_param: str) -> None:
        p = self._p("Conqueror")
        if p:
            self._conqueror_stacks = min(self._conqueror_stacks + p[stack_param], p["max_stacks"])
