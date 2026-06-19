from collections.abc import Mapping

DREAD_FIELDS = (
    "damage",
    "reproducibility",
    "exploitability",
    "affected_users",
    "discoverability",
)


def calculate_total_score(values: Mapping[str, int]) -> float:
    try:
        total = sum(int(values[field]) for field in DREAD_FIELDS)
    except KeyError as exc:
        raise ValueError(f"Missing DREAD field: {exc.args[0]}") from exc

    return round(total / len(DREAD_FIELDS), 2)


def determine_risk_level(total_score: float) -> str:
    if total_score < 3:
        return "Low"
    if total_score < 6:
        return "Medium"
    if total_score < 8:
        return "High"
    return "Critical"


def calculate_dread_score(values: Mapping[str, int]) -> tuple[float, str]:
    total_score = calculate_total_score(values)
    return total_score, determine_risk_level(total_score)
