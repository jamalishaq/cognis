from app.models.alert import NormalisedAlert
from app.registry import normaliser_registry


def normalise(payload: dict) -> NormalisedAlert:
    return normaliser_registry.normalise(payload)
