from app.models.champion import Champion


def test_load_lucian():
    champ = Champion.load("Lucian")
    assert champ.name == "루시안"
    assert champ.base_stats.attack_damage == 60.0


def test_stats_at_level_1_matches_base():
    champ = Champion.load("Lucian")
    stats = champ.stats_at_level(1)
    assert stats.hp == champ.base_stats.hp
    assert stats.attack_damage == champ.base_stats.attack_damage


def test_stats_grow_with_level():
    champ = Champion.load("Lucian")
    lvl1 = champ.stats_at_level(1)
    lvl18 = champ.stats_at_level(18)
    assert lvl18.hp > lvl1.hp
    assert lvl18.attack_damage > lvl1.attack_damage
    assert lvl18.armor > lvl1.armor


def test_invalid_level_raises():
    champ = Champion.load("Lucian")
    try:
        champ.stats_at_level(19)
        assert False, "레벨 19는 예외를 발생시켜야 함"
    except ValueError:
        pass
