"""설명(description) 파싱 테스트. 사용자 PC에서 받은 실제 Data Dragon 16.21.1 en_US 설명(tests/fixtures)을 사용."""
import json
from pathlib import Path

import pytest

from app.models.item import Item
from app.services.data_dragon import merge_item_data
from app.services.item_description import parse_passive, parse_stat_block

FIXTURE = Path(__file__).parent / "fixtures" / "ddragon_16.21.1_descriptions.json"


@pytest.fixture
def descriptions():
    return {i: e["description"] for i, e in json.loads(FIXTURE.read_text(encoding="utf-8"))["data"].items()}


def _api(descriptions, **overrides):
    """실제 설명으로 API 응답을 만든다 (stats 숫자는 비워 설명만 검증)."""
    return {i: {"stats": {}, "description": overrides.get(f"d{i}", d)} for i, d in descriptions.items()}


def test_stat_block_reads_stats_that_are_only_in_the_description(descriptions):
    assert parse_stat_block(descriptions["3031"]) == {
        "FlatPhysicalDamageMod": 75, "FlatCritChanceMod": 0.25, "crit_damage_bonus": 0.30,
    }
    assert parse_stat_block(descriptions["3036"])["PercentArmorPenetrationMod"] == 0.35
    assert parse_stat_block(descriptions["6676"])["Lethality"] == 10
    assert parse_stat_block(descriptions["3508"])["AbilityHaste"] == 20
    assert parse_stat_block(descriptions["6672"])["PercentMovementSpeedMod"] == 0.04
    assert parse_stat_block(descriptions["3006"])["FlatMovementSpeedMod"] == 45


def test_every_local_stat_matches_the_real_16_21_1_description(descriptions):
    # 로컬 data/items.json이 16.21.1 설명과 완전히 같아야 함 (API가 안 될 때도 최신 패치 값)
    for item_id, item in Item.read_raw()["data"].items():
        parsed = parse_stat_block(descriptions[item_id])
        local = dict(item["stats"])
        if "crit_damage_bonus" in item:
            local["crit_damage_bonus"] = item["crit_damage_bonus"]
        assert parsed == pytest.approx(local), item_id


@pytest.mark.parametrize(
    "item_id, key, expected",
    [
        ("3036", "GiantSlayer", {"max_amp": 0.15, "amp_per_100_bonus_health": 0.01}),
        ("6676", "Execute", {"health_threshold": 0.05}),
        ("3094", "Sharpshooter", {"damage": 40}),
        ("6675", "Transcendence", {"remaining_cooldown_reduction": 0.15}),
        ("2512", "OpeningBarrage",
         {"attacks": 3, "forced_crit_ratio": 0.8, "duration_seconds": 8, "true_damage_ratio": 0.15}),
        ("2523", "Magnification", {"max_amp": 0.10, "amp_per_50_units": 0.01}),
    ],
)
def test_passive_numbers_are_read_from_the_description(descriptions, item_id, key, expected):
    assert parse_passive(key, descriptions[item_id]) == pytest.approx(expected)


@pytest.mark.parametrize("item_id, key", [("6672", "BringItDown"), ("3078", "Spellblade"),
                                          ("3181", "Skipper"), ("3095", "Bolt"), ("3508", "Spellblade")])
def test_passives_without_numbers_in_the_description_are_not_parsed(descriptions, item_id, key):
    assert parse_passive(key, descriptions[item_id]) is None


def test_real_16_21_1_data_changes_nothing_and_reports_passive_sources(descriptions):
    local = Item.read_raw()
    merged, report = merge_item_data(local, _api(descriptions), "16.21.1")

    assert report.changes == []
    assert merged["data"] == local["data"]
    assert set(report.passive_from_api) == {"3036", "6676", "3094", "6675", "2512", "2523"}
    assert set(report.passive_local) == {"6672", "3078", "3181", "3095", "3508"}


def test_a_new_patch_updates_crit_damage_and_passive_numbers(descriptions):
    patched = _api(
        descriptions,
        d3031=descriptions["3031"].replace("30%</attention> Critical Strike Damage", "40%</attention> Critical Strike Damage"),
        d6676=descriptions["6676"].replace("below 5% Health", "below 7% Health"),
        d3094=descriptions["3094"].replace("40 bonus magic damage", "60 bonus magic damage"),
    )
    merged, report = merge_item_data(Item.read_raw(), patched, "16.22.1")
    items = Item.from_raw(merged)

    assert items["3031"].crit_damage_bonus == 0.40
    assert items["6676"].passive["health_threshold"] == pytest.approx(0.07)
    assert items["3094"].passive["damage"] == 60
    changed = {(c.item_id, c.stat) for c in report.changes}
    assert changed == {("3031", "crit_damage_bonus"), ("6676", "passive.health_threshold"), ("3094", "passive.damage")}


def test_unrecognized_description_keeps_local_passive(descriptions):
    local = Item.read_raw()
    garbled = _api(descriptions, d6676="<mainText><stats></stats>문장이 완전히 바뀜</mainText>")
    merged, report = merge_item_data(local, garbled, "16.22.1")

    assert merged["data"]["6676"]["passive"] == local["data"]["6676"]["passive"]
    assert merged["data"]["6676"]["stats"] == local["data"]["6676"]["stats"]
    assert "6676" in report.passive_local


def test_changes_have_korean_labels(descriptions):
    patched = _api(descriptions, d6676=descriptions["6676"].replace("below 5% Health", "below 7% Health"))
    _, report = merge_item_data(Item.read_raw(), patched, "16.22.1")
    assert [c.label for c in report.changes] == ["고유 효과: 처형 기준 체력"]
