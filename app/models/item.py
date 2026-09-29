"""아이템별 스탯 증가량 모델."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ._common import DATA_DIR

DEFAULT_ITEMS_PATH = DATA_DIR / "items.json"
MAX_ITEM_SLOTS = 6


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    plaintext: str
    stats: Dict[str, float] = field(default_factory=dict)
    crit_damage_bonus: float = 0.0  # 추가 치명타 피해량 (무한의 대검 패시브 등)

    @classmethod
    def load_all(cls, path: Optional[Path] = None) -> Dict[str, "Item"]:
        path = path or DEFAULT_ITEMS_PATH
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        items = {}
        for item_id, data in raw["data"].items():
            items[item_id] = cls(
                id=item_id,
                name=data["name"],
                plaintext=data.get("plaintext", ""),
                stats=data.get("stats", {}),
                crit_damage_bonus=data.get("crit_damage_bonus", 0.0),
            )
        return items

    @classmethod
    def load_by_id(cls, item_id: str, path: Optional[Path] = None) -> "Item":
        items = cls.load_all(path)
        if item_id not in items:
            raise KeyError(f"'{item_id}' 아이템을 {path or DEFAULT_ITEMS_PATH}에서 찾을 수 없습니다.")
        return items[item_id]

    # Data Dragon 스탯 키에 대한 편의 접근자 (예시 아이템 5종에서 쓰이는 것만 우선 지원)
    @property
    def attack_damage(self) -> float:
        return self.stats.get("FlatPhysicalDamageMod", 0.0)

    @property
    def crit_chance(self) -> float:
        return self.stats.get("FlatCritChanceMod", 0.0)

    @property
    def attack_speed_percent(self) -> float:
        return self.stats.get("PercentAttackSpeedMod", 0.0)

    @property
    def life_steal_percent(self) -> float:
        return self.stats.get("PercentLifeStealMod", 0.0)


@dataclass
class ItemBuild:
    """최대 6개 아이템으로 구성되는 장비 세트."""

    items: List[Item] = field(default_factory=list)

    def add(self, item: Item) -> None:
        if len(self.items) >= MAX_ITEM_SLOTS:
            raise ValueError(f"아이템은 최대 {MAX_ITEM_SLOTS}개까지 장착할 수 있습니다.")
        self.items.append(item)

    def total_stats(self) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for item in self.items:
            for stat, value in item.stats.items():
                totals[stat] = totals.get(stat, 0.0) + value
        return totals

    def crit_damage_bonus(self) -> float:
        # 무한의 대검 패시브는 고유(Unique) 효과라 여러 개를 껴도 중첩되지 않음 -> 합이 아닌 최댓값
        return max((item.crit_damage_bonus for item in self.items), default=0.0)
