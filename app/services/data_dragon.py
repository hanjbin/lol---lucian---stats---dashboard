"""Riot Data Dragon API에서 아이템 스탯 수치를 가져와 로컬 데이터(data/items.json)에 반영하는 모듈.

설계 원칙
- API로 갱신하는 것은 Data Dragon item.json의 stats에 실제로 들어 있는 스탯 수치(API_STAT_KEYS)뿐이다.
- 추가 치명타 피해량(crit_damage_bonus), 고유 효과(passive), 시작 아이템/신발 구분, 스킬 가속처럼
  Data Dragon에 없는 값은 로컬 data/items.json의 값을 그대로 쓴다 (API가 알려주지 않으므로).
- 네트워크가 안 되거나 응답 형식이 이상하면 예외를 밖으로 던지지 않고 로컬 데이터로 대체한다 (앱이 멈추지 않게).
- 추가 패키지 없이 표준 라이브러리(urllib)만 사용한다.
"""
import copy
import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.models.item import Item

BASE_URL = "https://ddragon.leagueoflegends.com"
DEFAULT_LOCALE = "ko_KR"
TIMEOUT_SECONDS = 5

# Data Dragon item.json의 stats에 들어 있는 스탯 키 -> API 값으로 갱신
# (AbilityHaste, PercentOmnivampMod, FlatMagicPenetrationMod, PercentTenacityMod는 stats에 없어
#  data/items.json에 설명 수치로 직접 넣은 값이므로 여기에 포함하지 않고 로컬 값을 유지)
API_STAT_KEYS = (
    "FlatPhysicalDamageMod",
    "FlatCritChanceMod",
    "PercentAttackSpeedMod",
    "PercentMovementSpeedMod",
    "FlatMovementSpeedMod",
    "FlatHPPoolMod",
    "FlatArmorMod",
    "FlatSpellBlockMod",
    "PercentLifeStealMod",
)

STAT_LABELS = {
    "FlatPhysicalDamageMod": "공격력",
    "FlatCritChanceMod": "치명타 확률",
    "PercentAttackSpeedMod": "공격속도",
    "PercentMovementSpeedMod": "이동속도(%)",
    "FlatMovementSpeedMod": "이동속도",
    "FlatHPPoolMod": "체력",
    "FlatArmorMod": "방어력",
    "FlatSpellBlockMod": "마법 저항력",
    "PercentLifeStealMod": "생명력 흡수",
}

ApiStats = Dict[str, Dict[str, float]]


def _get_json(url: str, timeout: float = TIMEOUT_SECONDS):
    request = urllib.request.Request(url, headers={"User-Agent": "lucian-damage-calculator"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_latest_version(timeout: float = TIMEOUT_SECONDS) -> str:
    """Data Dragon의 가장 최신 버전 문자열 (예: '16.19.1')."""
    versions = _get_json(f"{BASE_URL}/api/versions.json", timeout)
    if not isinstance(versions, list) or not versions or not isinstance(versions[0], str):
        raise ValueError("Data Dragon 버전 목록 형식이 예상과 다릅니다.")
    return versions[0]


def fetch_item_stats(
    version: str, locale: str = DEFAULT_LOCALE, timeout: float = TIMEOUT_SECONDS
) -> ApiStats:
    """해당 버전 item.json에서 {아이템 id: stats} 만 뽑아 반환."""
    raw = _get_json(f"{BASE_URL}/cdn/{version}/data/{locale}/item.json", timeout)
    data = raw["data"]
    if not isinstance(data, dict):
        raise ValueError("Data Dragon item.json의 data 형식이 예상과 다릅니다.")
    return {
        str(item_id): entry["stats"]
        for item_id, entry in data.items()
        if isinstance(entry, dict) and isinstance(entry.get("stats"), dict)
    }


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True)
class StatChange:
    """로컬 데이터 대비 API 값이 달랐던 스탯 하나."""

    item_id: str
    item_name: str
    stat: str
    old: Optional[float]
    new: float

    @property
    def label(self) -> str:
        return STAT_LABELS.get(self.stat, self.stat)


@dataclass
class MergeReport:
    changes: List[StatChange] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)  # API 응답에 없던 로컬 아이템 id


def merge_item_stats(local_raw: dict, api_stats: ApiStats, version: str):
    """로컬 items.json(dict)에 API 스탯 수치를 덮어쓴 새 dict와 변경 내역을 반환.

    - API_STAT_KEYS에 해당하고 API가 숫자로 준 값만 덮어쓴다 (없던 스탯이면 추가).
    - API 응답에 없는 스탯은 지우지 않고 로컬 값을 유지한다 (보수적으로 처리).
    - 원본 local_raw는 바꾸지 않는다.
    """
    merged = copy.deepcopy(local_raw)
    report = MergeReport()
    for item_id, item in merged["data"].items():
        api = api_stats.get(item_id)
        if api is None:
            report.missing.append(item_id)
            continue
        stats = item.setdefault("stats", {})
        for key in API_STAT_KEYS:
            value = api.get(key)
            if not _is_number(value):
                continue
            old = stats.get(key)
            if old is None or abs(old - value) > 1e-9:
                report.changes.append(StatChange(item_id, item["name"], key, old, float(value)))
            stats[key] = float(value)
    merged["version"] = version
    return merged, report


@dataclass
class ItemLoadResult:
    items: Dict[str, Item]
    source: str  # "api" 또는 "local"
    version: str  # 스탯 수치가 기준으로 하는 Data Dragon 버전
    local_version: str  # data/items.json에 적힌 버전
    changes: List[StatChange] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    error: Optional[str] = None  # API를 시도했다가 실패해 로컬로 대체한 경우 이유


def load_items(
    use_api: bool = True,
    path: Optional[Path] = None,
    fetch_version: Callable[[], str] = fetch_latest_version,
    fetch_stats: Callable[[str], ApiStats] = fetch_item_stats,
) -> ItemLoadResult:
    """아이템 데이터를 불러온다. use_api가 True면 Data Dragon 최신 수치를 반영하고, 실패하면 로컬 데이터를 쓴다."""
    local_raw = Item.read_raw(path)
    local_version = local_raw.get("version", "unknown")
    error = None

    if use_api:
        try:
            version = fetch_version()
            api_stats = fetch_stats(version)
            merged, report = merge_item_stats(local_raw, api_stats, version)
            if len(report.missing) == len(local_raw["data"]):
                raise ValueError("API 응답에 로컬 아이템이 하나도 없습니다.")
            return ItemLoadResult(
                items=Item.from_raw(merged),
                source="api",
                version=version,
                local_version=local_version,
                changes=report.changes,
                missing=report.missing,
            )
        except (OSError, ValueError, KeyError, TypeError) as e:
            # URLError/HTTPError/timeout은 OSError, JSON 파싱 실패는 ValueError
            error = f"{type(e).__name__}: {e}"

    return ItemLoadResult(
        items=Item.from_raw(local_raw),
        source="local",
        version=local_version,
        local_version=local_version,
        error=error,
    )
