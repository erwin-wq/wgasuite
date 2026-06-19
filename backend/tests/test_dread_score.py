import pytest

from app.services.dread import calculate_dread_score, calculate_total_score, determine_risk_level


def test_calculate_total_score_uses_average() -> None:
    score = calculate_total_score(
        {
            "damage": 10,
            "reproducibility": 8,
            "exploitability": 6,
            "affected_users": 4,
            "discoverability": 2,
        }
    )

    assert score == 6.0


def test_calculate_total_score_requires_all_fields() -> None:
    with pytest.raises(ValueError, match="Missing DREAD field"):
        calculate_total_score({"damage": 1})


@pytest.mark.parametrize(
    ("total_score", "risk_level"),
    [
        (0, "Low"),
        (2.9, "Low"),
        (3, "Medium"),
        (5.9, "Medium"),
        (6, "High"),
        (7.9, "High"),
        (8, "Critical"),
        (10, "Critical"),
    ],
)
def test_determine_risk_level(total_score: float, risk_level: str) -> None:
    assert determine_risk_level(total_score) == risk_level


def test_calculate_dread_score_returns_total_and_risk_level() -> None:
    total_score, risk_level = calculate_dread_score(
        {
            "damage": 8,
            "reproducibility": 8,
            "exploitability": 8,
            "affected_users": 8,
            "discoverability": 8,
        }
    )

    assert total_score == 8.0
    assert risk_level == "Critical"
