import logging

import structlog
from structlog.contextvars import merge_contextvars


def _add_service_context(_, __, event_dict: dict) -> dict:
    from app.config import settings  # lazy to avoid import at module load
    event_dict.setdefault("service", "cognis")
    event_dict.setdefault("environment", settings.environment)
    event_dict.setdefault("version", "0.1.0")
    return event_dict


def setup_logging() -> None:
    from app.config import settings

    shared_processors = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_service_context,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.environment == "local":
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]
    else:
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
