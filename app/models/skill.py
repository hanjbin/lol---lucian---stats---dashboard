"""챔피언 스킬(Q/W/E/R) 및 패시브 데이터 모델."""
import json
import math
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
    crit_chance_shot_scaling: float = 0.0

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
            crit_chance_shot_scaling=data.get("crit_chance_shot_scaling", 0.0),
        )

    def hit_count(self, crit_chance: float) -> int:
        """타격 수. 루시안 R은 치명타 확률만큼 발사 수가 늘어남 (위키 V26.01 기준).

        발사 수 = 기본 22 × (1 + 치명타확률)  -> 22~44발 (예: 치명타 40% -> 30.8 -> 30발)
        - 소수점은 버림: 반 발은 쏠 수 없고 툴팁도 "최대 N발"이라 버림으로 판단.
          게임 내부의 실제 반올림 방식은 위키에 없어 확인되지 않은 가정.
        - 추가 치명타 피해량(무한의 대검 등)에 따른 추가 발사(툴팁의 "+0~6")는
          정확한 공식이 확인되지 않아 미반영.
        """
        return math.floor(self.hits * (1 + self.crit_chance_shot_scaling * crit_chance))

    def raw_damage(
        self, rank: int, total_ad: float, bonus_ad: float, crit_chance: float = 0.0
    ) -> float:
        """방어력/마저 적용 전 피해량 (다단히트 스킬은 모든 타가 명중한다고 가정)."""
        i = rank - 1
        per_hit = (
            self.base_damage[i]
            + self.bonus_ad_ratio[i] * bonus_ad
            + self.total_ad_ratio[i] * total_ad
        )
        return per_hit * self.hit_count(crit_chance)

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
