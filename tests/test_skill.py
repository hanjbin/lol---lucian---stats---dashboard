import pytest

from app.models.skill import ChampionKit


def test_rank_at_level_follows_skill_order():
    kit = ChampionKit.load()
    assert [kit.rank_at_level(k, 1) for k in "QWER"] == [1, 0, 0, 0]
    assert [kit.rank_at_level(k, 3) for k in "QWER"] == [1, 1, 1, 0]
    assert kit.rank_at_level("R", 6) == 1
    assert [kit.rank_at_level(k, 18) for k in "QWER"] == [5, 5, 5, 3]


def test_rank_at_level_rejects_invalid_level():
    kit = ChampionKit.load()
    with pytest.raises(ValueError):
        kit.rank_at_level("Q", 19)


def test_cooldown_applies_ability_haste():
    q = ChampionKit.load().skills["Q"]
    assert q.cooldown_at(5, 0) == 5
    assert q.cooldown_at(5, 100) == 2.5


def test_q_scales_with_bonus_ad_and_r_hits_multiple_times():
    kit = ChampionKit.load()
    assert kit.skills["Q"].raw_damage(5, total_ad=200, bonus_ad=100) == 205 + 1.20 * 100
    assert kit.skills["R"].raw_damage(3, total_ad=200, bonus_ad=100) == (45 + 0.25 * 200) * 22


def test_passive_ratio_by_level():
    kit = ChampionKit.load()
    assert kit.passive_second_shot_ratio(1) == 0.50
    assert kit.passive_second_shot_ratio(7) == 0.55
    assert kit.passive_second_shot_ratio(18) == 0.60


def test_r_shot_count_scales_with_crit_chance_and_rounds_down():
    r = ChampionKit.load().skills["R"]
    assert r.hit_count(0.0) == 22
    assert r.hit_count(0.4) == 30  # 22 × 1.4 = 30.8 -> 버림
    assert r.hit_count(0.5) == 33
    assert r.hit_count(1.0) == 44


def test_r_raw_damage_uses_crit_scaled_shot_count():
    r = ChampionKit.load().skills["R"]
    assert r.raw_damage(3, total_ad=200, bonus_ad=100, crit_chance=0.4) == (45 + 0.25 * 200) * 30


def test_non_multi_hit_skills_ignore_crit_chance():
    q = ChampionKit.load().skills["Q"]
    assert q.hit_count(1.0) == 1
