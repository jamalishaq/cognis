import asyncio

import structlog
from aws_embedded_metrics import metric_scope

log = structlog.get_logger()


@metric_scope
async def _emit_metric(
    namespace: str, name: str, value: float, unit: str, dimensions: dict, metrics
) -> None:
    metrics.set_namespace(namespace)
    metrics.set_dimensions(dimensions)
    metrics.put_metric(name, value, unit)


def _emit(namespace: str, name: str, value: float, unit: str, dimensions: dict) -> None:
    try:
        asyncio.run(_emit_metric(namespace, name, value, unit, dimensions))
    except Exception as exc:
        log.warning("metric_emission_failed", namespace=namespace, metric=name, error=str(exc))


def emit_pipeline_metric(name: str, value: float, unit: str, dimensions: dict) -> None:
    _emit("Cognis/Pipeline", name, value, unit, dimensions)


def emit_judge_metric(name: str, value: float, unit: str, dimensions: dict) -> None:
    _emit("Cognis/Judge", name, value, unit, dimensions)


def emit_bedrock_metric(name: str, value: float, unit: str, dimensions: dict) -> None:
    _emit("Cognis/Bedrock", name, value, unit, dimensions)
