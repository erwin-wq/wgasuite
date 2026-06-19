from collections.abc import Mapping

DREAD_FIELDS = (
    "dread_damage",
    "dread_reproducibility",
    "dread_exploitability",
    "dread_affected_users",
    "dread_discoverability",
)


def calculate_dread_score(values: Mapping[str, int]) -> float:
    try:
        total = sum(int(values[field]) for field in DREAD_FIELDS)
    except KeyError as exc:
        raise ValueError(f"Missing DREAD field: {exc.args[0]}") from exc

    return round(total / len(DREAD_FIELDS), 2)
