"""Data Dragon API 연동 테스트. 실제 네트워크는 쓰지 않고 가짜 응답(fake)으로만 검증한다."""
import urllib.error

import pytest

from app.models.item import Item
from app.services import data_dragon
from app.services.data_dragon import (
    ItemLoadResult,
    fetch_item_stats,
    fetch_latest_version,
    load_items,
    merge_item_stats,
)

NEW_VERSION = "99.1.1"


@pytest.fixture
def local_raw():
    return Item.read_raw()


def fake_api_stats():
    # 무한의 대검 공격력 75 -> 80, 크라켄 공격속도 0.4 -> 0.5 로 패치됐다고 가정
    return {
        "3031": {"FlatPhysicalDamageMod": 80, "FlatCritChanceMod": 0.25},
        "6672": {"FlatPhysicalDamageMod": 45, "PercentAttackSpeedMod": 0.5, "PercentMovementSpeedMod": 0.04},
    }


def test_merge_overrides_api_stats_and_reports_changes(local_raw):
    merged, report = merge_item_stats(local_raw, fake_api_stats(), NEW_VERSION)

    assert merged["version"] == NEW_VERSION
    assert merged["data"]["3031"]["stats"]["FlatPhysicalDamageMod"] == 80.0
    assert merged["data"]["6672"]["stats"]["PercentAttackSpeedMod"] == 0.5

    changed = {(c.item_id, c.stat): (c.old, c.new) for c in report.changes}
    assert changed == {
        ("3031", "FlatPhysicalDamageMod"): (75.0, 80.0),
        ("6672", "PercentAttackSpeedMod"): (0.4, 0.5),
    }


def test_merge_keeps_fields_the_api_does_not_have(local_raw):
    merged, _ = merge_item_stats(local_raw, fake_api_stats(), NEW_VERSION)

    # 추가 치명타 피해량, 고유 효과는 Data Dragon에 없으므로 로컬 값 유지
    assert merged["data"]["3031"]["crit_damage_bonus"] == 0.3
    assert merged["data"]["6672"]["passive"] == local_raw["data"]["6672"]["passive"]


def test_merge_never_overwrites_manual_only_stats(local_raw):
    # 스킬 가속은 Data Dragon stats에 없어 직접 넣은 값 -> API가 뭘 주든 로컬 유지
    api = {"3158": {"AbilityHaste": 999, "FlatMovementSpeedMod": 50}}
    merged, report = merge_item_stats(local_raw, api, NEW_VERSION)

    assert merged["data"]["3158"]["stats"]["AbilityHaste"] == 10.0
    assert merged["data"]["3158"]["stats"]["FlatMovementSpeedMod"] == 50.0
    assert [c.stat for c in report.changes] == ["FlatMovementSpeedMod"]


def test_merge_reports_items_missing_from_api_and_keeps_them(local_raw):
    merged, report = merge_item_stats(local_raw, fake_api_stats(), NEW_VERSION)

    assert "3072" in report.missing  # 피바라기는 가짜 응답에 없음
    assert merged["data"]["3072"]["stats"] == local_raw["data"]["3072"]["stats"]


def test_merge_ignores_non_numeric_values(local_raw):
    api = {"3031": {"FlatPhysicalDamageMod": "많음", "FlatCritChanceMod": True}}
    merged, report = merge_item_stats(local_raw, api, NEW_VERSION)

    assert merged["data"]["3031"]["stats"] == local_raw["data"]["3031"]["stats"]
    assert report.changes == []


def test_merge_does_not_modify_original(local_raw):
    before = Item.read_raw()
    merge_item_stats(local_raw, fake_api_stats(), NEW_VERSION)
    assert local_raw == before


def test_load_items_without_api_never_calls_the_network():
    def boom(*args, **kwargs):
        raise AssertionError("네트워크를 호출하면 안 됩니다")

    result = load_items(use_api=False, fetch_version=boom, fetch_stats=boom)

    assert result.source == "local"
    assert result.error is None
    assert result.items == Item.load_all()


def test_load_items_uses_api_values_when_available():
    result = load_items(
        use_api=True,
        fetch_version=lambda: NEW_VERSION,
        fetch_stats=lambda version: fake_api_stats(),
    )

    assert result.source == "api"
    assert result.version == NEW_VERSION
    assert result.local_version == "16.19.1"
    assert result.items["3031"].attack_damage == 80.0
    assert result.items["3031"].crit_damage_bonus == 0.3  # 로컬 전용 필드 유지
    assert result.items["1055"].is_starter  # 도란의 검 구분 유지
    assert len(result.changes) == 2


def test_load_items_falls_back_to_local_when_network_fails():
    def offline():
        raise urllib.error.URLError("인터넷 연결 없음")

    result = load_items(use_api=True, fetch_version=offline)

    assert result.source == "local"
    assert "URLError" in result.error
    assert result.items == Item.load_all()


def test_load_items_falls_back_when_api_has_none_of_our_items():
    result = load_items(
        use_api=True, fetch_version=lambda: NEW_VERSION, fetch_stats=lambda version: {"9999": {}}
    )

    assert result.source == "local"
    assert result.error is not None


def test_load_items_falls_back_on_malformed_response():
    def bad_stats(version):
        raise KeyError("data")

    result = load_items(use_api=True, fetch_version=lambda: NEW_VERSION, fetch_stats=bad_stats)

    assert result.source == "local"
    assert "KeyError" in result.error


def test_fetch_latest_version_takes_first_entry(monkeypatch):
    monkeypatch.setattr(data_dragon, "_get_json", lambda url, timeout=5: ["16.21.1", "16.20.1"])
    assert fetch_latest_version() == "16.21.1"


def test_fetch_latest_version_rejects_empty_list(monkeypatch):
    monkeypatch.setattr(data_dragon, "_get_json", lambda url, timeout=5: [])
    with pytest.raises(ValueError):
        fetch_latest_version()


def test_fetch_item_stats_builds_url_and_extracts_stats(monkeypatch):
    seen = {}

    def fake_get_json(url, timeout=5):
        seen["url"] = url
        return {"data": {"3031": {"name": "x", "stats": {"FlatPhysicalDamageMod": 80}}, "9": {"name": "stats 없음"}}}

    monkeypatch.setattr(data_dragon, "_get_json", fake_get_json)
    stats = fetch_item_stats("16.21.1", locale="ko_KR")

    assert seen["url"] == "https://ddragon.leagueoflegends.com/cdn/16.21.1/data/ko_KR/item.json"
    assert stats == {"3031": {"FlatPhysicalDamageMod": 80}}


def test_result_type_is_item_load_result():
    assert isinstance(load_items(use_api=False), ItemLoadResult)
