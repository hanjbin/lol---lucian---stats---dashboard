"""방어력/마법저항력에 의한 피해 감소 공식."""


def damage_after_resist(raw_damage: float, resist: float) -> float:
    """방어력/마법저항력 감소 공식 (둘 다 동일). 음수 저항(관통 등)도 라이엇 공식대로 처리."""
    if resist >= 0:
        mitigation = 100 / (100 + resist)
    else:
        mitigation = 2 - 100 / (100 - resist)
    return raw_damage * mitigation
