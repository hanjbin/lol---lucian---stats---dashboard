"""상대 챔피언의 레벨별 방어력/마법저항력 모델 (단순화)."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from ._common import DATA_DIR, growth_factor

DEFAULT_OPPONENTS_PATH = DATA_DIR / "opponents.json"

# 아이템 개수 -> 예상 레벨 범위(최소, 최대) 매핑.
# 라이엇 공식 데이터가 아니라 "코어 아이템을 갖췄을 때 보통 이 정도 레벨이다"라는
# 일반적인 게임 진행 속도를 가정한 근사치이며, estimate_level_from_item_count에서
# 범위의 중간값을 사용한다.
ITEM_COUNT_LEVEL_RANGES: Dict[int, Tuple[int, int]] = {
    0: (1, 3),
    1: (6, 8),
    2: (9, 11),
    3: (11, 13),
    4: (13, 15),
    5: (15, 16),
    6: (16, 18),
}


def estimate_level_from_item_count(item_count: int) -> int:
    """아이템 개수를 기준으로 상대 챔피언의 예상 레벨을 추정 (근사치).

    ITEM_COUNT_LEVEL_RANGES에 매핑된 레벨 범위의 중간값(반올림)을 반환한다.
    실제 게임 진행 속도는 매치마다 다르므로 정확한 값이 아니라 참고용 추정치이며,
    이 값을 그대로 쓰고 싶지 않다면 UI에서 직접 레벨을 입력해 덮어쓸 수 있다.
    """
    max_item_count = max(ITEM_COUNT_LEVEL_RANGES)
    clamped_count = max(0, min(item_count, max_item_count))
    low, high = ITEM_COUNT_LEVEL_RANGES[clamped_count]
    return round((low + high) / 2)


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
