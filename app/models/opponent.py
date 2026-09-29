"""상대 챔피언의 레벨별 방어력/마법저항력 모델 (단순화)."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from ._common import DATA_DIR, growth_factor

DEFAULT_OPPONENTS_PATH = DATA_DIR / "opponents.json"


@dataclass(frozen=True)
class Opponent:
    id: str
    name: str
    armor: float
    armor_per_level: float
    magic_resist: float
    magic_resist_per_level: float

    @classmethod
    def load_all(cls, path: Optional[Path] = None) -> Dict[str, "Opponent"]:
        path = path or DEFAULT_OPPONENTS_PATH
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        return {
            o["id"]: cls(
                id=o["id"],
                name=o["name"],
                armor=o["armor"],
                armor_per_level=o["armor_per_level"],
                magic_resist=o["magic_resist"],
                magic_resist_per_level=o["magic_resist_per_level"],
            )
            for o in raw["opponents"]
        }

    @classmethod
    def load_by_id(cls, opponent_id: str, path: Optional[Path] = None) -> "Opponent":
        opponents = cls.load_all(path)
        if opponent_id not in opponents:
            raise KeyError(f"'{opponent_id}' 상대 정보를 {path or DEFAULT_OPPONENTS_PATH}에서 찾을 수 없습니다.")
        return opponents[opponent_id]

    def armor_at_level(self, level: int) -> float:
        return self.armor + self.armor_per_level * growth_factor(level)

    def magic_resist_at_level(self, level: int) -> float:
        return self.magic_resist + self.magic_resist_per_level * growth_factor(level)
