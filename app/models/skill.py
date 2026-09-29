"""챔피언 스킬(Q/W/E/R) 및 패시브 데이터 모델."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from ._common import DATA_DIR, MAX_LEVEL, MIN_LEVEL

DEFAULT_SKILLS_PATH = DATA_DIR / "skills.json"

PHYSICAL = "physical"
MAGIC = "magic"
NO_DAMAGE = "none"


@dataclass(frozen=True)
class Skill:
    key: str
    name: str
    damage_type: str
    cooldown: Tuple[float, ...]
    base_damage: Tuple[float, ...]
    bonus_ad_ratio: Tuple[float, ...]
    total_ad_ratio: Tuple[float, ...]
    hits: int = 1

    @classmethod
    def from_dict(cls, key: str, data: dict) -> "Skill":
        ranks = len(data["cooldown"])
        zeros = [0.0] * ranks
        return cls(
            key=key,
            name=data["name"],
            damage_type=data["damage_type"],
            cooldown=tuple(data["cooldown"]),
            base_damage=tuple(data.get("base_damage", zeros)),
            bonus_ad_ratio=tuple(data.get("bonus_ad_ratio", zeros)),
            total_ad_ratio=tuple(data.get("total_ad_ratio", zeros)),
            hits=data.get("hits", 1),
        )

    def raw_damage(self, rank: int, total_ad: float, bonus_ad: float) -> float:
        """방어력/마저 적용 전 피해량 (다단히트 스킬은 모든 타가 명중한다고 가정)."""
        i = rank - 1
        per_hit = (
            self.base_damage[i]
            + self.bonus_ad_ratio[i] * bonus_ad
            + self.total_ad_ratio[i] * total_ad
        )
        return per_hit * self.hits

    def cooldown_at(self, rank: int, ability_haste: float) -> float:
        # 스킬 가속 공식: 실제 쿨타임 = 기본 쿨타임 * 100 / (100 + 스킬 가속)
        return self.cooldown[rank - 1] * 100 / (100 + ability_haste)


@dataclass(frozen=True)
class ChampionKit:
    skills: Dict[str, Skill]
    skill_order: Tuple[str, ...]
    passive_name: str
    # (적용 시작 레벨, 비율) 오름차순
    passive_ratio_by_level: Tuple[Tuple[int, float], ...]

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ChampionKit":
        path = path or DEFAULT_SKILLS_PATH
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        passive = raw["passive"]
        ratios = sorted(
            (int(level), ratio)
            for level, ratio in passive["second_shot_total_ad_ratio_by_level"].items()
        )
        return cls(
            skills={key: Skill.from_dict(key, data) for key, data in raw["skills"].items()},
            skill_order=tuple(raw["skill_order"]),
            passive_name=passive["name"],
            passive_ratio_by_level=tuple(ratios),
        )

    def rank_at_level(self, skill_key: str, level: int) -> int:
        """skill_order 기준으로 해당 레벨까지 찍은 스킬 포인트 수 (0이면 아직 미습득)."""
        if not MIN_LEVEL <= level <= MAX_LEVEL:
            raise ValueError(f"레벨은 {MIN_LEVEL}~{MAX_LEVEL} 사이여야 합니다: {level}")
        return self.skill_order[:level].count(skill_key)

    def passive_second_shot_ratio(self, level: int) -> float:
        ratio = 0.0
        for min_level, value in self.passive_ratio_by_level:
            if level >= min_level:
                ratio = value
        return ratio
