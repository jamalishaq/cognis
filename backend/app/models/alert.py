from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GrafanaAlertItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}
    starts_at: datetime | None = Field(None, alias="startsAt")
    ends_at: datetime | None = Field(None, alias="endsAt")
    generator_url: str = Field("", alias="generatorURL")
    fingerprint: str = ""


class GrafanaPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    state: str
    message: str = ""
    alerts: list[GrafanaAlertItem] = []
    common_labels: dict[str, str] = Field(default_factory=dict, alias="commonLabels")
    common_annotations: dict[str, str] = Field(default_factory=dict, alias="commonAnnotations")
    external_url: str = Field("", alias="externalURL")
    receiver: str = ""
    status: str = ""
    group_key: str = Field("", alias="groupKey")
    org_id: int = Field(0, alias="orgId")


class PagerDutyService(BaseModel):
    id: str = ""
    summary: str = ""
    type: str = ""


class PagerDutyIncidentBody(BaseModel):
    type: str = ""
    details: str = ""


class PagerDutyIncidentData(BaseModel):
    id: str
    title: str
    status: str
    incident_key: str = ""
    created_at: datetime
    html_url: str = ""
    urgency: str = ""
    service: PagerDutyService = Field(default_factory=PagerDutyService)
    body: PagerDutyIncidentBody = Field(default_factory=PagerDutyIncidentBody)


class PagerDutyEvent(BaseModel):
    id: str
    event_type: str
    resource_type: str = "incident"
    occurred_at: datetime
    data: PagerDutyIncidentData


class PagerDutyPayload(BaseModel):
    event: PagerDutyEvent


class NormalisedAlert(BaseModel):
    source: Literal["grafana", "pagerduty", "generic"]
    title: str
    description: str
    severity: Literal["critical", "high", "medium", "low", "unknown"] = "unknown"
    service: str = ""
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime
