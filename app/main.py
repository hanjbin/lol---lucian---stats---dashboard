# Streamlit 앱 진입점
import sys
from pathlib import Path

# streamlit run app/main.py로 실행하면 스크립트가 있는 app/ 디렉터리만
# sys.path에 잡혀 프로젝트 루트의 app 패키지를 찾지 못함 -> 루트를 직접 추가.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataclasses import replace

import streamlit as st

from app.models._common import MAX_LEVEL, MIN_LEVEL
from app.models.champion import Champion
from app.models.item import Item, ItemBuild, MAX_ITEM_SLOTS
from app.models.opponent import Opponent, estimate_level_from_item_count
from app.models.rune import NO_EFFECT, Rune, RunePage, RuneTree
from app.models.skill import ChampionKit
from app.services.combo_calculator import (
    DPS_COMBO_DURATION,
    ComboResult,
    burst_combo,
    dps_combo,
)
from app.services.damage_calculator import (
    auto_attack_dps,
    combine_stats,
    expected_auto_attack_damage,
)


def combo_table(result: ComboResult) -> list:
    return [
        {
            **({"시각(초)": f"{e.time:.2f}"} if e.time is not None else {}),
            "행동": e.action,
            "데미지": round(e.damage, 1),
        }
        for e in result.events
    ]


def rune_label(rune: Rune) -> str:
    return f"{rune.name} (데미지 영향 없음)" if rune.effect == NO_EFFECT else rune.name


def tree_label(tree: RuneTree) -> str:
    return tree.name


st.set_page_config(page_title="루시안 딜량 계산기", page_icon="🗡️")
st.title("루시안 딜량 계산기")

champion = Champion.load("Lucian")
kit = ChampionKit.load()
items = Item.load_all()
rune_trees = RuneTree.load_all()
opponents = Opponent.load_all()

with st.sidebar:
    st.header("루시안 설정")
    level = st.slider("레벨", MIN_LEVEL, MAX_LEVEL, 11)

    item_names = [item.name for item in items.values()]
    selected_item_names = st.multiselect(
        f"아이템 (최대 {MAX_ITEM_SLOTS}개)", item_names, max_selections=MAX_ITEM_SLOTS
    )

    extra_ability_haste = st.number_input(
        "추가 스킬 가속 (아이템/룬 외)", min_value=0, max_value=300, value=0, step=5
    )

    st.header("상대 설정")
    opponent_id = st.selectbox(
        "상대 챔피언",
        list(opponents.keys()),
        format_func=lambda oid: opponents[oid].name,
    )

    estimated_opponent_level = estimate_level_from_item_count(len(selected_item_names))
    manual_level_override = st.checkbox("상대 레벨 직접 입력 (자동 추정 대신 사용)")
    if manual_level_override:
        opponent_level = st.slider(
            "상대 레벨 (수동)", MIN_LEVEL, MAX_LEVEL, estimated_opponent_level
        )
    else:
        opponent_level = estimated_opponent_level
        st.caption(
            f"아이템 {len(selected_item_names)}개 기준 자동 추정 레벨: {opponent_level} "
            "(공식 데이터가 아닌 일반적인 게임 진행 속도 근사치)"
        )
    target_health_percent = st.slider("상대 현재 체력 (%)", 1, 100, 100)
    st.caption("최후의 일격(40% 미만)·체력차 극복(60% 초과) 발동 판정용. 콤보 중에는 변하지 않는다고 가정.")

    st.header("룬")
    primary_tree = st.selectbox(
        "메인 룬 트리",
        [t for t in rune_trees.values() if t.allow_primary],
        format_func=tree_label,
    )
    keystone = st.selectbox(
        "핵심 룬", primary_tree.keystones, format_func=rune_label, key=f"keystone_{primary_tree.key}"
    )
    primary_runes = tuple(
        st.selectbox(
            f"메인 슬롯 {i}", row, format_func=rune_label, key=f"primary_{primary_tree.key}_{i}"
        )
        for i, row in enumerate(primary_tree.minor_rows, start=1)
    )

    secondary_tree = st.selectbox(
        "보조 룬 트리",
        [t for t in rune_trees.values() if t.allow_secondary and t.key != primary_tree.key],
        format_func=tree_label,
        key=f"secondary_tree_{primary_tree.key}",
    )
    secondary_rows = secondary_tree.minor_rows
    secondary_runes = st.multiselect(
        "보조 룬 (서로 다른 슬롯에서 2개)",
        [r for row in secondary_rows for r in row],
        default=[secondary_rows[0][0], secondary_rows[1][0]],
        format_func=lambda r: f"[슬롯 {r.row}] {rune_label(r)}",
        max_selections=2,
        key=f"secondary_{secondary_tree.key}",
    )

    try:
        rune_page = RunePage(
            primary_tree=primary_tree,
            keystone=keystone,
            primary_runes=primary_runes,
            secondary_tree=secondary_tree,
            secondary_runes=tuple(secondary_runes),
        )
    except ValueError as e:
        rune_page = None
        st.error(f"{e} 룬 효과를 제외하고 계산합니다.")

item_by_name = {item.name: item for item in items.values()}
item_build = ItemBuild()
for name in selected_item_names:
    item_build.add(item_by_name[name])

champion_stats = champion.stats_at_level(level)
combined = combine_stats(champion_stats, item_build, rune_page)
combined = replace(combined, ability_haste=combined.ability_haste + extra_ability_haste)
opponent = opponents[opponent_id]

st.subheader("합산 스탯")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("공격력", f"{combined.attack_damage:.1f}")
col2.metric("공격속도", f"{combined.attack_speed:.2f}")
col3.metric("치명타 확률", f"{combined.crit_chance * 100:.0f}%")
col4.metric("치명타 피해량", f"{combined.crit_damage * 100:.0f}%")
col5.metric("생명흡수", f"{combined.life_steal_percent * 100:.0f}%")

st.subheader(f"{opponent.name} (레벨 {opponent_level}) 대상 평타 딜량")
single_hit = expected_auto_attack_damage(combined, opponent, opponent_level)
dps = auto_attack_dps(combined, opponent, opponent_level)

col1, col2 = st.columns(2)
col1.metric("평타 1회 기대 데미지", f"{single_hit:.1f}")
col2.metric("초당 평타 데미지 (DPS)", f"{dps:.1f}")

st.caption(
    "치명타는 확률 기반 기댓값으로 계산합니다 (치명타 피해량 기본 200%, 무한의 대검 보유 시 230%). "
    "이 섹션에는 상시 스탯 룬(전설 룬 등)만 반영되고, 조건부 룬(집중 공격, 감전 등)은 "
    "아래 스킬 콤보에서 발동 조건을 판단해 반영합니다. 그 외 아이템 특수 효과는 미포함."
)

st.subheader("스킬 콤보")
ranks = ", ".join(f"{key} {kit.rank_at_level(key, level)}" for key in "QWER")
st.caption(
    f"레벨 {level} 스킬 랭크: {ranks} (표준 스킬 트리 기준) · 스킬 가속 {combined.ability_haste:.0f}"
)

target_health_ratio = target_health_percent / 100
dps_result = dps_combo(
    kit, level, combined, opponent, opponent_level, rune_page, target_health_ratio
)
burst_result = burst_combo(
    kit, level, combined, opponent, opponent_level, rune_page, target_health_ratio
)

dps_col, burst_col = st.columns(2)
with dps_col:
    st.markdown(f"**DPS 콤보 ({DPS_COMBO_DURATION:.0f}초)**")
    st.caption("E → 평타 → Q → 평타 → W → 평타 → 이후 평타 + 쿨 돌아오면 스킬 즉시 사용 (R 제외)")
    st.metric(f"{DPS_COMBO_DURATION:.0f}초간 총 데미지", f"{dps_result.total_damage:.1f}")
    st.metric("DPS", f"{dps_result.dps:.1f}")
    with st.expander("타임라인"):
        st.dataframe(combo_table(dps_result), hide_index=True)
with burst_col:
    st.markdown("**폭딜 콤보**")
    st.caption("E → 평타 → Q → 평타 → W → 평타 → R → 평타 (1회, 시간 제한 없음)")
    st.metric("총 데미지", f"{burst_result.total_damage:.1f}")
    if kit.rank_at_level("R", level) > 0:
        st.caption(
            f"R 발사 수: {kit.skills['R'].hit_count(combined.crit_chance)}발 "
            "(22 × (1 + 치명타 확률), 소수점 버림)"
        )
    with st.expander("시퀀스"):
        st.dataframe(combo_table(burst_result), hide_index=True)

st.caption(
    "가정: 스킬 시전 시간·투사체 이동 시간 0, 평타는 공격속도 간격으로 꾸준히 발생, "
    "스킬 사용 후 다음 평타는 패시브(빛의 사도)로 2연발, 스킬은 전부 명중, AP 0. "
    "평타는 치명타 기댓값 적용, R은 치명타 확률만큼 발사 수만 증가하고 "
    "탄환에 치명타 피해는 적용하지 않음. 룬 발동 피해는 타임라인에 룬 이름으로 표시되며, "
    "룬 관련 가정(레벨 비례 수치 선형 보간, 전설 룬 최대 스택, 패시브 2연발은 탄환마다 공격 1회 등)은 "
    "app/services/rune_effects.py 참고."
)
