"""챔피언 레벨별 기본 스탯 모델 (루시안 등)."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ._common import DATA_DIR, growth_factor

DEFAULT_CHAMPIONS_PATH = DATA_DIR / "champions.json"


@dataclass(frozen=True)
class ChampionBaseStats:
    hp: float
    hp_per_level: float
    mp: float
    mp_per_level: float
    armor: float
    armor_per_level: float
    magic_resist: float
    magic_resist_per_level: float
    attack_damage: float
    attack_damage_per_level: float
    attack_speed: float
    attack_speed_per_level: float  # 레벨당 증가율(%), Data Dragon attackspeedperlevel과 동일
    move_speed: float
    attack_range: float

    @classmethod
    def from_ddragon(cls, stats: dict) -> "ChampionBaseStats":
        return cls(
            hp=stats["hp"],
            hp_per_level=stats["hpperlevel"],
            mp=stats["mp"],
            mp_per_level=stats["mpperlevel"],
            armor=stats["armor"],
            armor_per_level=stats["armorperlevel"],
            magic_resist=stats["spellblock"],
            magic_resist_per_level=stats["spellblockperlevel"],
            attack_damage=stats["attackdamage"],
            attack_damage_per_level=stats["attackdamageperlevel"],
            attack_speed=stats["attackspeed"],
            attack_speed_per_level=stats["attackspeedperlevel"],
            move_speed=stats["movespeed"],
            attack_range=stats["attackrange"],
        )


@dataclass(frozen=True)
class ChampionStatsAtLevel:
    level: int
    hp: float
    mp: float
    armor: float
    magic_resist: float
    attack_damage: float
    attack_speed: float


@dataclass(frozen=True)
class Champion:
    id: str
    key: str
    name: str
    title: str
    base_stats: ChampionBaseStats

    @classmethod
    def load(cls, champion_id: str = "Lucian", path: Optional[Path] = None) -> "Champion":
        path = path or DEFAULT_CHAMPIONS_PATH
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        champ_data = raw["data"].get(champion_id)
        if champ_data is None:
            raise KeyError(f"'{champion_id}' 챔피언을 {path}에서 찾을 수 없습니다.")

        return cls(
            id=champ_data["id"],
            key=champ_data["key"],
            name=champ_data["name"],
            title=champ_data["title"],
            base_stats=ChampionBaseStats.from_ddragon(champ_data["stats"]),
        )

    def stats_at_level(self, level: int) -> ChampionStatsAtLevel:
        g = growth_factor(level)
        b = self.base_stats

        # 공격속도는 라이엇 실제 공식상 보너스 공격속도 비율로 누적되는 방식이 더 정확하지만,
        # 여기서는 다른 스탯과 동일한 성장 공식으로 단순화함 - TODO: 정확한 공식으로 교체.
        attack_speed = b.attack_speed * (1 + b.attack_speed_per_level / 100 * g)

        return ChampionStatsAtLevel(
            level=level,
            hp=b.hp + b.hp_per_level * g,
            mp=b.mp + b.mp_per_level * g,
            armor=b.armor + b.armor_per_level * g,
            magic_resist=b.magic_resist + b.magic_resist_per_level * g,
            attack_damage=b.attack_damage + b.attack_damage_per_level * g,
            attack_speed=attack_speed,
        )
