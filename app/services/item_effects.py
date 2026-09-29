"""아이템 고유 효과(패시브) 중 콤보 데미지에 영향을 주는 것.

구현한 효과 (League of Legends 위키 기준, 루시안은 원거리라 원거리 수치 사용 - data/items.json의 passive):
- 크라켄 학살자 (끌어내리기): 기본 공격 적중 시 스택(4초 유지, 최대 2). 2스택에서 다음 기본 공격이
  스택을 모두 소모해 120~168(레벨 비례) 추가 물리 피해 -> 3번째 적중마다 발동.
  대상의 잃은 체력에 비례해 0~75% 증가 (잃은 체력 비율에 선형 비례한다고 가정, UI의 "상대 현재 체력" 사용).
- 삼위일체 (주문검): 스킬 사용 후 10초 안의 다음 기본 공격에 기본 공격력의 200% 추가 물리 피해.
  재사용 대기시간 1.5초 (강화 공격 후 시작). 대기시간 중 사용한 스킬은 주문검을 충전하지 않는다고 가정.
- 선체파괴자 (선장): 기본 공격 적중 시 스택(10초 유지). 5번째 공격마다 기본 공격력 84% + 대상 최대 체력 3.5%
  추가 물리 피해.

모델링하지 않은 효과 (1:1 데미지와 무관): 루난의 허리케인 추가 화살(주변 다른 적 대상), 피바라기 보호막,
판금 장화 피해 감소, 이동 속도 효과 등. 무한의 대검 치명타 피해량은 CombinedStats.crit_damage에 반영됨.

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


@dataclass(frozen=True)
class ItemProc:
    name: str
    raw_physical_damage: float  # 방어력/룬 증폭 적용 전


class ItemCombat:
    """콤보 1회 동안 아이템 고유 효과의 스택/쿨다운을 추적하며 발동 여부를 판단."""

    def __init__(
        self,
        item_build: Optional[ItemBuild],
        level: int,
        stats: "CombinedStats",
        target_health_ratio: float,
        target_max_health: float,
    ):
        self.level = level
        self.stats = stats
        self.target_health_ratio = target_health_ratio
        self.target_max_health = target_max_health
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

    @property
    def _base_attack_damage(self) -> float:
        return self.stats.attack_damage - self.stats.bonus_attack_damage

    def on_skill_cast(self, t: float) -> None:
        p = self._passives.get("Spellblade")
        if p and t >= self._spellblade_ready_at:
            self._spellblade_until = t + p["duration_seconds"]

    def on_attack_hit(self, t: float) -> List[ItemProc]:
        """기본 공격 탄환 1발 적중 시 발동하는 아이템 효과."""
        procs: List[ItemProc] = []

        p = self._passives.get("Spellblade")
        if p and self._spellblade_until is not None and t <= self._spellblade_until:
            procs.append(ItemProc(p["name"], p["base_ad_ratio"] * self._base_attack_damage))
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

        return procs

    @staticmethod
    def _expired(last_hit: Optional[float], t: float, passive: dict) -> bool:
        return last_hit is not None and t - last_hit > passive["stack_duration_seconds"]
