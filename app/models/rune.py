"""룬 트리 / 룬 페이지 모델 (실제 롤 룬 페이지 구조)."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from ._common import DATA_DIR

DEFAULT_RUNES_PATH = DATA_DIR / "runes.json"

STAT = "stat"
COMBO = "combo"
NO_EFFECT = "none"

KEYSTONE_ROW = 0
SECONDARY_RUNE_COUNT = 2


@dataclass(frozen=True)
class Rune:
    id: int
    key: str
    name: str
    tree_key: str
    row: int  # 0 = 키스톤, 1~3 = 일반 슬롯
    effect: str  # "stat" | "combo" | "none"
    params: Dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def is_keystone(self) -> bool:
        return self.row == KEYSTONE_ROW


@dataclass(frozen=True)
class RuneTree:
    key: str
    name: str
    allow_primary: bool
    allow_secondary: bool
    slots: Tuple[Tuple[Rune, ...], ...]

    @property
    def keystones(self) -> Tuple[Rune, ...]:
        return self.slots[KEYSTONE_ROW]

    @property
    def minor_rows(self) -> Tuple[Tuple[Rune, ...], ...]:
        return self.slots[KEYSTONE_ROW + 1 :]

    def rune(self, key: str) -> Rune:
        for row in self.slots:
            for rune in row:
                if rune.key == key:
                    return rune
        raise KeyError(f"'{key}' 룬이 {self.name} 트리에 없습니다.")

    @classmethod
    def load_all(cls, path: Optional[Path] = None) -> Dict[str, "RuneTree"]:
        path = path or DEFAULT_RUNES_PATH
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        trees = {}
        for t in raw["trees"]:
            slots = tuple(
                tuple(
                    Rune(
                        id=r["id"],
                        key=r["key"],
                        name=r["name"],
                        tree_key=t["key"],
                        row=row_index,
                        effect=r["effect"],
                        params=r.get("params", {}),
                    )
                    for r in row
                )
                for row_index, row in enumerate(t["slots"])
            )
            trees[t["key"]] = cls(
                key=t["key"],
                name=t["name"],
                allow_primary=t["primary"],
                allow_secondary=t["secondary"],
                slots=slots,
            )
        return trees


@dataclass(frozen=True)
class RunePage:
    """메인 룬: 트리 1개에서 키스톤 1개 + 슬롯 1~3에서 각각 1개.
    보조 룬: 메인과 다른 트리에서 서로 다른 슬롯(1~3)의 룬 2개 (키스톤 불가)."""

    primary_tree: RuneTree
    keystone: Rune
    primary_runes: Tuple[Rune, ...]
    secondary_tree: RuneTree
    secondary_runes: Tuple[Rune, ...]

    def __post_init__(self) -> None:
        if not self.primary_tree.allow_primary:
            raise ValueError(f"{self.primary_tree.name} 트리는 메인 룬으로 선택할 수 없습니다.")
        if not self.secondary_tree.allow_secondary:
            raise ValueError(f"{self.secondary_tree.name} 트리는 보조 룬으로 선택할 수 없습니다.")
        if self.primary_tree.key == self.secondary_tree.key:
            raise ValueError("보조 룬 트리는 메인 룬 트리와 달라야 합니다.")

        if self.keystone not in self.primary_tree.keystones:
            raise ValueError(f"{self.keystone.name}은(는) {self.primary_tree.name} 트리의 키스톤이 아닙니다.")

        minor_rows = self.primary_tree.minor_rows
        if len(self.primary_runes) != len(minor_rows):
            raise ValueError(f"메인 룬은 슬롯마다 1개씩 {len(minor_rows)}개를 골라야 합니다.")
        for rune, row in zip(self.primary_runes, minor_rows):
            if rune not in row:
                raise ValueError(f"{rune.name}은(는) 해당 메인 룬 슬롯에 속하지 않습니다.")

        if len(self.secondary_runes) != SECONDARY_RUNE_COUNT:
            raise ValueError(f"보조 룬은 {SECONDARY_RUNE_COUNT}개를 골라야 합니다.")
        secondary_minor = [r for row in self.secondary_tree.minor_rows for r in row]
        for rune in self.secondary_runes:
            if rune not in secondary_minor:
                raise ValueError(f"{rune.name}은(는) {self.secondary_tree.name} 트리의 일반 슬롯 룬이 아닙니다.")
        if len({rune.row for rune in self.secondary_runes}) != SECONDARY_RUNE_COUNT:
            raise ValueError("보조 룬 2개는 서로 다른 슬롯에서 골라야 합니다.")

    @property
    def runes(self) -> Tuple[Rune, ...]:
        return (self.keystone, *self.primary_runes, *self.secondary_runes)

    def get(self, key: str) -> Optional[Rune]:
        return next((r for r in self.runes if r.key == key), None)
