"""방어력/마법저항력에 의한 피해 감소 공식."""


def damage_after_resist(raw_damage: float, resist: float) -> float:
    """방어력/마법저항력 감소 공식 (둘 다 동일). 음수 저항(관통 등)도 라이엇 공식대로 처리."""
    if resist >= 0:
        mitigation = 100 / (100 + resist)
    else:
        mitigation = 2 - 100 / (100 - resist)
    return raw_damage * mitigation


def effective_armor(armor: float, armor_pen_percent: float = 0.0, lethality: float = 0.0) -> float:
    """방어구 관통(%) -> 물리 관통력(치명성) 순서로 적용한 대상의 실질 방어력 (위키 Armor penetration).

    - 치명성은 V14.1부터 레벨과 무관하게 1:1 고정 방어구 관통력.
    - 관통은 방어력을 0 아래로 내리지 못함 (방어력이 0 이하면 관통 효과 없음).
    """
    if armor <= 0:
        return armor
    armor *= 1 - armor_pen_percent
    return max(armor - lethality, 0.0)
