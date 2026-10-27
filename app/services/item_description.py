"""Data Dragon 아이템 설명(description) 문장에서 숫자를 읽어오는 모듈.

Data Dragon item.json의 stats에는 공격력/공격속도/치명타 확률 같은 기본 스탯만 숫자로 들어 있고,
치명타 피해량, 방어구 관통, 물리 관통력, 스킬 가속, 고유 효과 수치는 설명 문장에만 적혀 있다.
그래서 en_US 설명을 읽어 이 숫자들도 패치에 맞춰 갱신한다.

설명 형식 (Data Dragon 16.21.1 en_US 실제 데이터, tests/fixtures 참고):
  <mainText><stats><attention>75</attention> Attack Damage<br><attention>30%</attention> Critical Strike Damage</stats>
  <br><br><passive>Giant Slayer</passive><br>Deal up to 15% bonus damage ... at 1500 bonus Health.</mainText>

원칙
- 정해진 문장 패턴에 정확히 맞을 때만 숫자를 쓰고, 패턴이 안 맞거나 숫자가 없으면(예: 크라켄 학살자는
  "bonus physical damage"라고만 적혀 있음) None을 돌려줘 로컬 data/items.json 값을 유지하게 한다.
- 문장이 바뀌어 패턴이 안 맞아도 앱이 멈추지 않고 로컬 값으로 계산된다.
"""
import re
from typing import Callable, Dict, Optional

# 설명 스탯 이름 -> (data/items.json의 stats 키, 퍼센트 여부)
# 이동 속도는 %가 붙으면 PercentMovementSpeedMod, 아니면 FlatMovementSpeedMod.
STAT_NAME_TO_KEY = {
    "Attack Damage": "FlatPhysicalDamageMod",
    "Critical Strike Chance": "FlatCritChanceMod",
    "Attack Speed": "PercentAttackSpeedMod",
    "Health": "FlatHPPoolMod",
    "Armor": "FlatArmorMod",
    "Magic Resist": "FlatSpellBlockMod",
    "Life Steal": "PercentLifeStealMod",
    "Ability Haste": "AbilityHaste",
    "Omnivamp": "PercentOmnivampMod",
    "Magic Penetration": "FlatMagicPenetrationMod",
    "Tenacity": "PercentTenacityMod",
    "Armor Penetration": "PercentArmorPenetrationMod",
    "Lethality": "Lethality",
}
CRIT_DAMAGE_STAT = "Critical Strike Damage"  # 무한의 대검 추가 치명타 피해량 -> crit_damage_bonus 필드

_STATS_BLOCK = re.compile(r"<stats>(.*?)</stats>", re.S)
_STAT_LINE = re.compile(r"<attention>\s*([\d.]+)\s*(%?)\s*</attention>\s*([A-Za-z ]+?)\s*(?=<br|$)")
_TAG = re.compile(r"<[^>]+>")
_NUM = r"(\d+(?:\.\d+)?)"


def parse_stat_block(description: str) -> Dict[str, float]:
    """설명의 <stats> 부분을 {stats 키 또는 'crit_damage_bonus': 값}으로. 퍼센트는 0~1 비율로 바꾼다."""
    match = _STATS_BLOCK.search(description or "")
    if not match:
        return {}
    result: Dict[str, float] = {}
    for number, percent, name in _STAT_LINE.findall(match.group(1)):
        value = float(number) / 100 if percent else float(number)
        if name == CRIT_DAMAGE_STAT:
            result["crit_damage_bonus"] = value
        elif name == "Move Speed":
            result["PercentMovementSpeedMod" if percent else "FlatMovementSpeedMod"] = value
        elif name in STAT_NAME_TO_KEY:
            result[STAT_NAME_TO_KEY[name]] = value
    return result


def plain_text(description: str) -> str:
    """태그를 지운 설명 문장 (<stats> 부분 제외)."""
    body = _STATS_BLOCK.sub("", description or "")
    return re.sub(r"\s+", " ", _TAG.sub(" ", body)).strip()


def _search(pattern: str, text: str):
    return re.search(pattern, text, re.I)


def _giant_slayer(text: str) -> Optional[dict]:
    m = _search(rf"up to {_NUM}% bonus damage against champions based on their bonus Health.*?"
                rf"at {_NUM} bonus Health", text)
    if not m:
        return None
    max_amp = float(m.group(1)) / 100
    return {"max_amp": max_amp, "amp_per_100_bonus_health": max_amp / (float(m.group(2)) / 100)}


def _execute(text: str) -> Optional[dict]:
    m = _search(rf"executes champions that are below {_NUM}% Health", text)
    return {"health_threshold": float(m.group(1)) / 100} if m else None


def _energized(text: str) -> Optional[dict]:
    # 래피드파이어: "Energized Attack deals 40 bonus magic damage" / 스톰레이저는 숫자 없이 "applies bonus magic damage"
    m = _search(rf"Energized Attack (?:deals|applies) {_NUM} bonus magic damage", text)
    return {"damage": float(m.group(1))} if m else None


def _transcendence(text: str) -> Optional[dict]:
    m = _search(rf"reduce Basic Ability cooldowns by {_NUM}% of their remaining cooldown", text)
    return {"remaining_cooldown_reduction": float(m.group(1)) / 100} if m else None


def _opening_barrage(text: str) -> Optional[dict]:
    attacks = _search(r"your next (\d+) basic attacks", text)
    crit = _search(rf"Critically Strike for {_NUM}% of your normal Critical Strike damage for {_NUM} seconds", text)
    true = _search(rf"{_NUM}% bonus true damage", text)
    if not (attacks and crit and true):
        return None
    return {
        "attacks": int(attacks.group(1)),
        "forced_crit_ratio": float(crit.group(1)) / 100,
        "duration_seconds": float(crit.group(2)),
        "true_damage_ratio": float(true.group(1)) / 100,
    }


def _magnification(text: str) -> Optional[dict]:
    m = _search(rf"up to {_NUM}% increased damage with Attacks.*?max damage at {_NUM} range", text)
    if not m:
        return None
    max_amp = float(m.group(1)) / 100
    return {"max_amp": max_amp, "amp_per_50_units": max_amp / (float(m.group(2)) / 50)}


# 고유 효과 key -> 설명에서 수치를 읽는 함수.
# 크라켄(BringItDown), 주문검(Spellblade), 선체파괴자(Skipper), 스톰레이저(Bolt)는 설명에 숫자가 없어 로컬 값 사용.
PASSIVE_PARSERS: Dict[str, Callable[[str], Optional[dict]]] = {
    "GiantSlayer": _giant_slayer,
    "Execute": _execute,
    "Sharpshooter": _energized,
    "Bolt": _energized,
    "Transcendence": _transcendence,
    "OpeningBarrage": _opening_barrage,
    "Magnification": _magnification,
}


def parse_passive(key: str, description: str) -> Optional[dict]:
    """고유 효과 수치를 설명에서 읽는다. 읽을 수 없으면 None (로컬 값 유지)."""
    parser = PASSIVE_PARSERS.get(key)
    return parser(plain_text(description)) if parser else None
