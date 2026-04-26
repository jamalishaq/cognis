from app.models.alert import NormalisedAlert
from app.providers.base import AlertNormaliser
from app.providers.normalisers.generic import GenericNormaliser
from app.providers.normalisers.grafana import GrafanaNormaliser
from app.providers.normalisers.pagerduty import PagerDutyNormaliser

_NORMALISERS: list[AlertNormaliser] = [
    GrafanaNormaliser(),
    PagerDutyNormaliser(),
    GenericNormaliser(),  # always last — fallback that accepts any payload
]


def normalise(payload: dict) -> NormalisedAlert:
    for normaliser in _NORMALISERS:
        if normaliser.can_handle(payload):
            return normaliser.normalise(payload)
    raise RuntimeError("No normaliser matched payload")  # pragma: no cover