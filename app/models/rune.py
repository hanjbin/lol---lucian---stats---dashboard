"""룬별 효과 모델 (고정 수치 위주로 단순화, 조건부 효과는 원시 데이터만 보존)."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ._common import DATA_DIR

DEFAULT_RUNES_PATH = DATA_DIR / "runes.json"

FLAT_STAT = "flat_stat"
CONDITIONAL = "conditional"


@dataclass(frozen=True)
class Rune:
    id: int
    key: str
    name: str
    tree: str
    type: str  # "flat_stat" | "conditional"
    stats: Dict[str, float] = field(default_factory=dict)
    condition: Optional[dict] = None
    note: str = ""

    @classmethod
    def load_all(cls, path: Optional[Path] = None) -> List["Rune"]:
        path = path or DEFAULT_RUNES_PATH
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        return [
            cls(
                id=r["id"],
                key=r["key"],
                name=r["name"],
                tree=r["tree"],
                type=r["type"],
                stats=r.get("stats", {}),
                condition=r.get("condition"),
                note=r.get("note", ""),
            )
            for r in raw["runes"]
        ]

    @classmethod
    def load_by_key(cls, key: str, path: Optional[Path] = None) -> "Rune":
        for rune in cls.load_all(path):
            if rune.key == key:
                return rune
        raise KeyError(f"'{key}' 룬을 {path or DEFAULT_RUNES_PATH}에서 찾을 수 없습니다.")

    @property
    def is_conditional(self) -> bool:
        return self.type == CONDITIONAL
