"""models 패키지 공용 유틸리티."""
from pathlib import Path

# app/models/_common.py 기준 -> parents[2] == 프로젝트 루트
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

MIN_LEVEL = 1
MAX_LEVEL = 18


def growth_factor(level: int) -> float:
    """라이엇 공식 챔피언 스탯 성장 공식.

    stat(level) = base + growth * factor(level)
    factor(level) = (level - 1) * (0.7025 + 0.0175 * (level - 1))
    """
    if not MIN_LEVEL <= level <= MAX_LEVEL:
        raise ValueError(f"레벨은 {MIN_LEVEL}~{MAX_LEVEL} 사이여야 합니다: {level}")
    return (level - 1) * (0.7025 + 0.0175 * (level - 1))
