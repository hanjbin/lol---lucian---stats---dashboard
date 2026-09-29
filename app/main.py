# Streamlit 앱 진입점
import sys
from pathlib import Path

# streamlit run app/main.py로 실행하면 스크립트가 있는 app/ 디렉터리만
# sys.path에 잡혀 프로젝트 루트의 app 패키지를 찾지 못함 -> 루트를 직접 추가.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from app.models._common import MAX_LEVEL, MIN_LEVEL
from app.models.champion import Champion
from app.models.item import Item, ItemBuild, MAX_ITEM_SLOTS
from app.models.opponent import Opponent
from app.models.rune import Rune
from app.services.damage_calculator import (
    auto_attack_dps,
    combine_stats,
    expected_auto_attack_damage,
)

st.set_page_config(page_title="루시안 딜량 계산기", page_icon="🗡️")
st.title("루시안 딜량 계산기")

champion = Champion.load("Lucian")
items = Item.load_all()
runes = Rune.load_all()
opponents = Opponent.load_all()

with st.sidebar:
    st.header("루시안 설정")
    level = st.slider("레벨", MIN_LEVEL, MAX_LEVEL, 11)

    item_names = [item.name for item in items.values()]
    selected_item_names = st.multiselect(
        f"아이템 (최대 {MAX_ITEM_SLOTS}개)", item_names, max_selections=MAX_ITEM_SLOTS
    )

    flat_stat_runes = [r for r in runes if not r.is_conditional]
    conditional_runes = [r for r in runes if r.is_conditional]
    rune_names = [r.name for r in flat_stat_runes]
    selected_rune_names = st.multiselect("룬 (고정 수치만 지원)", rune_names)
    if conditional_runes:
        st.caption(
            "조건부 룬은 아직 계산에 반영되지 않습니다: "
            + ", ".join(r.name for r in conditional_runes)
        )

    st.header("상대 설정")
    opponent_id = st.selectbox(
        "상대 챔피언",
        list(opponents.keys()),
        format_func=lambda oid: opponents[oid].name,
    )
    opponent_level = st.slider("상대 레벨", MIN_LEVEL, MAX_LEVEL, 11)

item_by_name = {item.name: item for item in items.values()}
item_build = ItemBuild()
for name in selected_item_names:
    item_build.add(item_by_name[name])

rune_by_name = {r.name: r for r in flat_stat_runes}
selected_runes = [rune_by_name[name] for name in selected_rune_names]

champion_stats = champion.stats_at_level(level)
combined = combine_stats(champion_stats, item_build, selected_runes)
opponent = opponents[opponent_id]

st.subheader("합산 스탯")
col1, col2, col3, col4 = st.columns(4)
col1.metric("공격력", f"{combined.attack_damage:.1f}")
col2.metric("공격속도", f"{combined.attack_speed:.2f}")
col3.metric("치명타 확률", f"{combined.crit_chance * 100:.0f}%")
col4.metric("생명흡수", f"{combined.life_steal_percent * 100:.0f}%")

st.subheader(f"{opponent.name} (레벨 {opponent_level}) 대상 평타 딜량")
single_hit = expected_auto_attack_damage(combined, opponent, opponent_level)
dps = auto_attack_dps(combined, opponent, opponent_level)

col1, col2 = st.columns(2)
col1.metric("평타 1회 기대 데미지", f"{single_hit:.1f}")
col2.metric("초당 평타 데미지 (DPS)", f"{dps:.1f}")

st.caption(
    "치명타 피해 배율은 기본값(175%)만 반영하며, 스킬 데미지·룬 조건부 효과·"
    "아이템 특수 효과(무한의 검 치명타 피해 증가 등)는 아직 계산에 포함되지 않습니다."
)
