"""아이템 고유 효과(패시브) 중 콤보 데미지에 영향을 주는 것.

구현한 효과 (수치는 data/items.json의 passive. Data Dragon 설명에 숫자가 있는 효과는 API 연결 시 최신 값으로 갱신,
없는 효과는 League of Legends 위키 기준 원거리 수치):
- 크라켄 학살자 (끌어내리기): 기본 공격 적중 시 스택(4초 유지, 최대 2). 2스택에서 다음 기본 공격이
  스택을 모두 소모해 120~168(레벨 비례) 추가 물리 피해 -> 3번째 적중마다 발동.
  대상의 잃은 체력에 비례해 0~75% 증가 (잃은 체력 비율에 선형 비례한다고 가정, UI의 "상대 현재 체력" 사용).
- 삼위일체 (주문검): 스킬 사용 후 10초 안의 다음 기본 공격에 기본 공격력의 200% 추가 물리 피해.
  재사용 대기시간 1.5초 (강화 공격 후 시작). 대기시간 중 사용한 스킬은 주문검을 충전하지 않는다고 가정.
- 선체파괴자 (선장): 기본 공격 적중 시 스택(10초 유지). 5번째 공격마다 기본 공격력 84% + 대상 최대 체력 3.5%
  추가 물리 피해.
- 정수 약탈자 (주문검): 스킬 사용 후 다음 기본 공격에 기본 공격력의 125% + (치명타 확률 × 50%) 추가 물리 피해.
  "치명타 확률에 비례해 최대 50%"를 치명타 확률에 선형 비례한다고 가정. 삼위일체와 같은 주문검 계열이라 1개만 장착.
- 도미닉 경의 인사: 방어구 관통 35%(스탯, damage_calculator에서 반영) + 거인 학살자: 대상의 추가 체력
  100당 피해량 1% 증가(최대 15%). 상대 아이템을 모델링하지 않으므로 추가 체력은 UI 입력값 사용(기본 0).
- 필멸자의 운명: 방어구 관통 30%(스탯). 치유 감소는 데미지와 무관.
- 징수의 총: 물리 관통력 10(스탯) + 처형: 콤보 후 대상 체력이 최대 체력의 5% 미만으로 남으면 남은 체력만큼 처형 피해.
- 스톰레이저 / 래피드파이어 대포 (충전): 충전 상태의 다음 기본 공격에 추가 마법 피해 100 / 40.
  교전 전 이동으로 이미 완전 충전되어 있다고 보고 콤보 첫 공격에 1회만 적용 (콤보 중 재충전은 미반영).
- 나보리 신속검 (초월): 기본 공격 시 기본 스킬(Q/W/E)의 남은 재사용 대기시간 15% 감소 (평타 1회당 1번,
  패시브 2연발의 두 번째 탄환은 별도 공격으로 보지 않음).
- 악마사냥꾼의 화살 (개시 사격): 궁극기 사용 후 8초 안의 다음 기본 공격 3회가 강화되어, 치명타가 아니면
  일반 치명타 피해의 80%로 치명타, 원래 치명타면 일반 치명타 + 공격 피해(경감 전)의 15% 고정 피해 (재사용 45초).
  기댓값으로 계산하고 2연발 탄환은 각각 1회로 셈. 공격속도 50% 증가는 R을 쓰는 폭딜 콤보에 시간 개념이 없어 미반영.
- 헥스옵틱 C44 (확대): 대상과의 거리 50당 기본 공격 피해 1% 증가(최대 10%). 루시안 사거리(500) 끝에서
  공격한다고 가정해 최대치 10% 적용.

모델링하지 않은 효과 (1:1 데미지와 무관): 루난의 허리케인 추가 화살(주변 다른 적 대상), 피바라기 보호막,
불멸의 철갑궁 보호막, 유령 무희 유령 상태, 필멸자의 운명 치유 감소, 악마사냥꾼의 화살 궁극기 가속,
헥스옵틱 처치 시 사거리 증가, 판금 장화 피해 감소, 이동 속도 효과 등. 무한의 대검 치명타 피해량은 CombinedStats.crit_damage에 반영됨.

가정:
- 패시브(빛의 사도) 2연발의 두 번째 탄환도 적중 시 효과를 적용하므로(위키) 크라켄/선체파괴자 스택은 탄환마다 쌓음.
  주문검은 강화 공격 1회에 소모되므로 첫 탄환에만 적용.
- 아이템 추가 피해는 치명타가 없고, 룬의 피해 증폭(집중 공격, 선제공격 등)은 적용 (combo_calculator에서 처리).
- 기본 공격력 = 레벨 기준 공격력 (아이템/룬/정복자로 얻은 추가 공격력 제외).
- 폭딜 콤보는 한순간(t=0)으로 보므로 주문검은 콤보당 1회만 발동.
- 같은 고유 효과 아이템을 여러 개 넣어도 효과는 1번만 적용 (고유 효과).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

from app.models.item import ItemBuild
from app.services.rune_effects import level_scaled

if TYPE_CHECKING:
    from app.services.damage_calculator import CombinedStats


PHYSICAL_DAMAGE = "physical"
MAGIC_DAMAGE = "magic"
TRUE_DAMAGE = "true"
BASIC_ABILITIES = ("Q", "W", "E")


@dataclass(frozen=True)
class ItemProc:
    name: str
    raw_damage: float  # 방어력/마법 저항력/룬 증폭 적용 전
    damage_type: str = PHYSICAL_DAMAGE


class ItemCombat:
    """콤보 1회 동안 아이템 고유 효과의 스택/쿨다운을 추적하며 발동 여부를 판단."""

    def __init__(
        self,
        item_build: Optional[ItemBuild],
        level: int,
        stats: "CombinedStats",
        target_health_ratio: float,
        target_max_health: float,
        target_bonus_health: float = 0.0,
    ):
        self.level = level
        self.stats = stats
        self.target_health_ratio = target_health_ratio
        self.target_max_health = target_max_health
        self.target_bonus_health = target_bonus_health
        self._passives: Dict[str, dict] = {}
        for item in item_build.items if item_build else ():
            if item.passive:
                self._passives.setdefault(item.passive["key"], item.passive)

        self._kraken_stacks = 0
        self._kraken_last_hit: Optional[float] = None
        self._skipper_stacks = 0
        self._skipper_last_hit: Optional[float] = None
        self._spellblade_until: Optional[float] = None
        self._spellblade_ready_at = float("-inf")
        self._energized_used = False
        self._barrage_charges = 0
        self._barrage_until: Optional[float] = None
        self._barrage_ready_at = float("-inf")

    @property
    def _base_attack_damage(self) -> float:
        return self.stats.attack_damage - self.stats.bonus_attack_damage

    def damage_multiplier(self) -> float:
        """모든 피해에 곱하는 배율 (도미닉 경의 인사 거인 학살자)."""
        p = self._passives.get("GiantSlayer")
        if not p:
            return 1.0
        amp = p["amp_per_100_bonus_health"] * max(self.target_bonus_health, 0.0) / 100
        return 1 + min(amp, p["max_amp"])

    def basic_attack_multiplier(self) -> float:
        """기본 공격 피해에만 곱하는 배율 (헥스옵틱 C44 확대)."""
        p = self._passives.get("Magnification")
        if not p:
            return 1.0
        return 1 + min(p["amp_per_50_units"] * p["assumed_distance"] / 50, p["max_amp"])

    @property
    def remaining_cooldown_reduction(self) -> float:
        """기본 공격 시 기본 스킬 남은 재사용 대기시간 감소 비율 (나보리 신속검)."""
        p = self._passives.get("Transcendence")
        return p["remaining_cooldown_reduction"] if p else 0.0

    def on_skill_cast(self, t: float, key: str = "") -> None:
        p = self._passives.get("Spellblade")
        if p and t >= self._spellblade_ready_at:
            self._spellblade_until = t + p["duration_seconds"]

        p = self._passives.get("OpeningBarrage")
        if p and key == "R" and t >= self._barrage_ready_at:
            self._barrage_charges = p["attacks"]
            self._barrage_until = t + p["duration_seconds"]
            self._barrage_ready_at = t + p["cooldown"]

    def shot_crit(self, t: float):
        """탄환 1발의 (치명타 기댓값 배율, 경감 전 피해 대비 기대 고정 피해 비율).

        악마사냥꾼의 화살 강화 공격이면 강화 횟수를 1 소모하고 강화된 기댓값을 돌려준다.
        """
        c = self.stats.crit_chance
        p = self._passives.get("OpeningBarrage")
        if (
            p
            and self._barrage_charges > 0
            and self._barrage_until is not None
            and t <= self._barrage_until
        ):
            self._barrage_charges -= 1
            # 치명타가 아니던 공격(1-c): 일반 치명타 피해의 80%로 강제 치명타, 원래 치명타(c): 일반 치명타 + 고정 피해
            crit_damage = self.stats.crit_damage
            factor = (1 - c) * crit_damage * p["forced_crit_ratio"] + c * crit_damage
            true_ratio = c * self.stats.crit_damage * p["true_damage_ratio"]
            return factor, true_ratio, p["name"]
        return self.stats.expected_crit_factor, 0.0, None

    def execute_damage(self, total_damage: float) -> float:
        """징수의 총 처형: 콤보 후 남은 체력이 최대 체력의 일정 비율 미만이면 남은 체력만큼 추가 피해."""
        p = self._passives.get("Execute")
        if not p:
            return 0.0
        remaining = self.target_health_ratio * self.target_max_health - total_damage
        if 0 < remaining < p["health_threshold"] * self.target_max_health:
            return remaining
        return 0.0

    def on_attack_hit(self, t: float) -> List[ItemProc]:
        """기본 공격 탄환 1발 적중 시 발동하는 아이템 효과."""
        procs: List[ItemProc] = []

        p = self._passives.get("Spellblade")
        if p and self._spellblade_until is not None and t <= self._spellblade_until:
            ratio = p["base_ad_ratio"] + p.get("crit_chance_base_ad_ratio", 0.0) * self.stats.crit_chance
            procs.append(ItemProc(p["name"], ratio * self._base_attack_damage))
            self._spellblade_until = None
            self._spellblade_ready_at = t + p["cooldown"]

        p = self._passives.get("BringItDown")
        if p:
            if self._expired(self._kraken_last_hit, t, p):
                self._kraken_stacks = 0
            self._kraken_last_hit = t
            if self._kraken_stacks == p["attacks_required"] - 1:
                missing_health = 1 - self.target_health_ratio
                damage = level_scaled(p["damage"], self.level) * (
                    1 + p["missing_health_amp"] * missing_health
                )
                procs.append(ItemProc(p["name"], damage))
                self._kraken_stacks = 0
            else:
                self._kraken_stacks += 1

        p = self._passives.get("Skipper")
        if p:
            if self._expired(self._skipper_last_hit, t, p):
                self._skipper_stacks = 0
            self._skipper_last_hit = t
            if self._skipper_stacks == p["attacks_required"] - 1:
                damage = (
                    p["base_ad_ratio"] * self._base_attack_damage
                    + p["target_max_health_ratio"] * self.target_max_health
                )
                procs.append(ItemProc(p["name"], damage))
                self._skipper_stacks = 0
            else:
                self._skipper_stacks += 1

        if not self._energized_used:
            # 충전 효과(스톰레이저, 래피드파이어 대포)는 콤보 첫 탄환에 1회
            for p in self._passives.values():
                if p.get("type") == "energized":
                    procs.append(ItemProc(p["name"], p["damage"], p.get("damage_type", PHYSICAL_DAMAGE)))
            self._energized_used = True

        return procs

    @staticmethod
    def _expired(last_hit: Optional[float], t: float, passive: dict) -> bool:
        return last_hit is not None and t - last_hit > passive["stack_duration_seconds"]
