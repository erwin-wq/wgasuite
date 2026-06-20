from pydantic import BaseModel


class GoogleWorkspaceCheckRead(BaseModel):
    check_id: str
    title: str
    category: str
    risk_statement: str
    description: str
    recommendation: str
    mock_status: str
    data_source_hint: str
    future_google_api_hint: str
    default_dread_score: dict[str, int]
    default_risk_level: str
    maps_to_finding_title: str
