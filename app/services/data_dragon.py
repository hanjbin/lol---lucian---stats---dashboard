"""Riot Data Dragon API에서 아이템 수치를 가져와 로컬 데이터(data/items.json)에 반영하는 모듈.

갱신하는 값
1. stats의 기본 스탯(API_STAT_KEYS): Data Dragon item.json의 stats 숫자 그대로.
2. 설명(description)에만 있는 스탯(DESCRIPTION_STAT_KEYS)과 추가 치명타 피해량(crit_damage_bonus):
   설명의 <stats> 목록에서 읽음 (services/item_description.py).
3. 고유 효과(passive) 수치: 설명 문장에 숫자가 적혀 있는 효과만 읽어서 갱신. 숫자가 없는 효과
   (크라켄 학살자, 주문검, 선체파괴자, 스톰레이저)는 로컬 값을 유지하고 화면에 그렇게 표시한다.

원칙
- 시작 아이템/신발 구분, 같은 계열 그룹처럼 Data Dragon에 없는 정보는 로컬 data/items.json 값을 쓴다.
- 네트워크가 안 되거나 응답 형식이 이상하면 예외를 밖으로 던지지 않고 로컬 데이터로 대체한다 (앱이 멈추지 않게).
- 설명은 문장 패턴이 일정한 en_US를 읽는다 (아이템 이름은 로컬 한국어 이름을 그대로 쓰므로 언어와 무관).
- 추가 패키지 없이 표준 라이브러리(urllib)만 사용한다.
"""
import copy
import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.models.item import Item
from app.services.item_description import parse_passive, parse_stat_block

BASE_URL = "https://ddragon.leagueoflegends.com"
DEFAULT_LOCALE = "en_US"
TIMEOUT_SECONDS = 5

# Data Dragon item.json의 stats에 들어 있는 스탯 키 -> stats 숫자로 갱신
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
# stats에는 없고 설명의 스탯 목록에만 있는 키 -> 설명에서 읽어 갱신
DESCRIPTION_STAT_KEYS = (
    "AbilityHaste",
    "PercentOmnivampMod",
    "FlatMagicPenetrationMod",
    "PercentTenacityMod",
    "PercentArmorPenetrationMod",
    "Lethality",
)
CRIT_DAMAGE_FIELD = "crit_damage_bonus"

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
    "AbilityHaste": "스킬 가속",
    "PercentOmnivampMod": "모든 피해 흡혈",
    "FlatMagicPenetrationMod": "마법 관통력",
    "PercentTenacityMod": "강인함",
    "PercentArmorPenetrationMod": "방어구 관통",
    "Lethality": "물리 관통력",
    CRIT_DAMAGE_FIELD: "추가 치명타 피해량",
}

PASSIVE_FIELD_LABELS = {
    "max_amp": "최대 피해 증가",
    "amp_per_100_bonus_health": "추가 체력 100당 피해 증가",
    "health_threshold": "처형 기준 체력",
    "damage": "추가 피해",
    "remaining_cooldown_reduction": "남은 쿨타임 감소",
    "attacks": "강화 공격 횟수",
    "forced_crit_ratio": "강제 치명타 피해 비율",
    "duration_seconds": "지속 시간(초)",
    "true_damage_ratio": "고정 피해 비율",
    "amp_per_50_units": "거리 50당 피해 증가",
}

ApiItems = Dict[str, dict]  # {아이템 id: {"stats": {...}, "description": "..."}}


def _get_json(url: str, timeout: float = TIMEOUT_SECONDS):
    request = urllib.request.Request(url, headers={"User-Agent": "lucian-damage-calculator"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_latest_version(timeout: float = TIMEOUT_SECONDS) -> str:
    """Data Dragon의 가장 최신 버전 문자열 (예: '16.21.1')."""
    versions = _get_json(f"{BASE_URL}/api/versions.json", timeout)
    if not isinstance(versions, list) or not versions or not isinstance(versions[0], str):
        raise ValueError("Data Dragon 버전 목록 형식이 예상과 다릅니다.")
    return versions[0]


def fetch_item_data(
    version: str, locale: str = DEFAULT_LOCALE, timeout: float = TIMEOUT_SECONDS
) -> ApiItems:
    """해당 버전 item.json에서 {아이템 id: {stats, description}} 만 뽑아 반환."""
    raw = _get_json(f"{BASE_URL}/cdn/{version}/data/{locale}/item.json", timeout)
    data = raw["data"]
    if not isinstance(data, dict):
        raise ValueError("Data Dragon item.json의 data 형식이 예상과 다릅니다.")
    return {
        str(item_id): {
            "stats": entry["stats"],
            "description": entry.get("description") if isinstance(entry.get("description"), str) else "",
        }
        for item_id, entry in data.items()
        if isinstance(entry, dict) and isinstance(entry.get("stats"), dict)
    }


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True)
class StatChange:
    """로컬 데이터 대비 API 값이 달랐던 수치 하나."""

    item_id: str
    item_name: str
    stat: str
    old: Optional[float]
    new: float

    @property
    def label(self) -> str:
        if self.stat.startswith("passive."):
            field_name = self.stat.split(".", 1)[1]
            return f"고유 효과: {PASSIVE_FIELD_LABELS.get(field_name, field_name)}"
        return STAT_LABELS.get(self.stat, self.stat)


@dataclass
class MergeReport:
    changes: List[StatChange] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)  # API 응답에 없던 로컬 아이템 id
    passive_from_api: List[str] = field(default_factory=list)  # 설명에서 고유 효과 수치를 읽은 아이템 id
    passive_local: List[str] = field(default_factory=list)  # 설명에 숫자가 없어 고유 효과에 로컬 값을 쓴 아이템 id


def _set(target: dict, key: str, value: float, item_id: str, item: dict, report: MergeReport, stat: str) -> None:
    old = target.get(key)
    if old is None or abs(old - value) > 1e-9:
        report.changes.append(StatChange(item_id, item["name"], stat, old, float(value)))
    target[key] = value if isinstance(value, int) else float(value)  # 공격 횟수 같은 정수는 정수로 유지


def merge_item_data(local_raw: dict, api_items: ApiItems, version: str):
    """로컬 items.json(dict)에 API 수치를 덮어쓴 새 dict와 변경 내역을 반환.

    - API가 숫자로 준 값만 덮어쓴다 (없던 스탯이면 추가). API에 없는 값은 지우지 않고 로컬 값을 유지.
    - 원본 local_raw는 바꾸지 않는다.
    """
    merged = copy.deepcopy(local_raw)
    report = MergeReport()
    for item_id, item in merged["data"].items():
        api = api_items.get(item_id)
        if api is None:
            report.missing.append(item_id)
            continue
        stats = item.setdefault("stats", {})
        api_stats = api.get("stats") or {}
        for key in API_STAT_KEYS:
            if _is_number(api_stats.get(key)):
                _set(stats, key, api_stats[key], item_id, item, report, key)

        description = api.get("description") or ""
        described = parse_stat_block(description)
        for key in DESCRIPTION_STAT_KEYS:
            if key in described:
                _set(stats, key, described[key], item_id, item, report, key)
        if CRIT_DAMAGE_FIELD in described:
            _set(item, CRIT_DAMAGE_FIELD, described[CRIT_DAMAGE_FIELD], item_id, item, report, CRIT_DAMAGE_FIELD)

        passive = item.get("passive")
        if passive:
            parsed = parse_passive(passive["key"], description)
            if parsed:
                for field_name, value in parsed.items():
                    _set(passive, field_name, value, item_id, item, report, f"passive.{field_name}")
                report.passive_from_api.append(item_id)
            else:
                report.passive_local.append(item_id)
    merged["version"] = version
    return merged, report


@dataclass
class ItemLoadResult:
    items: Dict[str, Item]
    source: str  # "api" 또는 "local"
    version: str  # 수치가 기준으로 하는 Data Dragon 버전
    local_version: str  # data/items.json에 적힌 버전
    changes: List[StatChange] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    passive_from_api: List[str] = field(default_factory=list)
    passive_local: List[str] = field(default_factory=list)
    error: Optional[str] = None  # API를 시도했다가 실패해 로컬로 대체한 경우 이유


def load_items(
    use_api: bool = True,
    path: Optional[Path] = None,
    fetch_version: Callable[[], str] = fetch_latest_version,
    fetch_items: Callable[[str], ApiItems] = fetch_item_data,
) -> ItemLoadResult:
    """아이템 데이터를 불러온다. use_api가 True면 Data Dragon 최신 수치를 반영하고, 실패하면 로컬 데이터를 쓴다."""
    local_raw = Item.read_raw(path)
    local_version = local_raw.get("version", "unknown")
    error = None

    if use_api:
        try:
            version = fetch_version()
            api_items = fetch_items(version)
            merged, report = merge_item_data(local_raw, api_items, version)
            if len(report.missing) == len(local_raw["data"]):
                raise ValueError("API 응답에 로컬 아이템이 하나도 없습니다.")
            return ItemLoadResult(
                items=Item.from_raw(merged),
                source="api",
                version=version,
                local_version=local_version,
                changes=report.changes,
                missing=report.missing,
                passive_from_api=report.passive_from_api,
                passive_local=report.passive_local,
            )
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            # URLError/HTTPError/timeout은 OSError, JSON 파싱 실패는 ValueError
            error = f"{type(e).__name__}: {e}"

    return ItemLoadResult(
        items=Item.from_raw(local_raw),
        source="local",
        version=local_version,
        local_version=local_version,
        error=error,
    )
