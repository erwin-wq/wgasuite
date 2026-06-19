import pytest

from app.services.dread import calculate_dread_score


def test_calculate_dread_score_uses_average() -> None:
    score = calculate_dread_score(
        {
            "dread_damage": 10,
            "dread_reproducibility": 8,
            "dread_exploitability": 6,
            "dread_affected_users": 4,
            "dread_discoverability": 2,
        }
    )

    assert score == 6.0


def test_calculate_dread_score_requires_all_fields() -> None:
    with pytest.raises(ValueError, match="Missing DREAD field"):
        calculate_dread_score({"dread_damage": 1})
