import boto3
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --- Always from environment / ECS task definition ---
    environment: Literal["local", "dev", "prod"] = "local"
    aws_region: str = "us-east-1"

    # --- Local dev only (empty in deployed environments) ---
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    dynamodb_endpoint: str = ""
    sqs_endpoint: str = ""

    # --- Feature flags (set by Terraform per environment in ECS task def) ---
    s3_vectors_mock: bool = False
    ses_mode: Literal["send", "log"] = "log"
    auth_disabled: bool = False

    # --- Parameter Store path prefix (set by Terraform in ECS task def) ---
    # e.g. /cognis/dev or /cognis/prod
    ssm_prefix: str = "/cognis/local"

    # --- Resolved from Parameter Store in deployed envs, .env.local locally ---
    # These are populated by _load_from_ssm() below when environment != local
    s3_vectors_bucket_name: str = ""
    s3_vectors_index_name: str = ""
    notification_queue_url: str = ""
    ingestion_queue_url: str = ""
    reasoning_model_id: str = "claude-sonnet-4-6"
    chat_model_id: str = "claude-sonnet-4-6"
    triage_model_id: str = "claude-haiku-4-5-20251001"
    judge_model_id: str = "claude-haiku-4-5-20251001"
    embedding_model_id: str = "cohere.embed-english-v4:0"
    rerank_model_id: str = "cohere.rerank-v3-5:0"
    active_notification_providers: str = "ses"
    ses_from_email: str = ""
    ses_to_emails: str = ""
    frontend_origin: str = ""

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @property
    def ses_to_emails_list(self) -> list[str]:
        return [e.strip() for e in self.ses_to_emails.split(",") if e.strip()]

    @property
    def active_providers_list(self) -> list[str]:
        return [p.strip() for p in self.active_notification_providers.split(",") if p.strip()]


# Parameter Store key → Settings field name mapping
_SSM_PARAM_MAP = {
    "s3-vectors-bucket-name":        "s3_vectors_bucket_name",
    "s3-vectors-index-name":         "s3_vectors_index_name",
    "sqs/notification-queue-url":    "notification_queue_url",
    "sqs/ingestion-queue-url":       "ingestion_queue_url",
    "reasoning-model-id":            "reasoning_model_id",
    "chat-model-id":                 "chat_model_id",
    "triage-model-id":               "triage_model_id",
    "judge-model-id":                "judge_model_id",
    "embedding-model-id":            "embedding_model_id",
    "rerank-model-id":               "rerank_model_id",
    "active-notification-providers": "active_notification_providers",
    "ses/sender-address":            "ses_from_email",
    "ses/recipient-addresses":       "ses_to_emails",
    "frontend-origin":               "frontend_origin",
}


def _load_from_ssm(settings: Settings) -> Settings:
    """
    Fetches config from Parameter Store in batch and overrides settings fields.
    Only runs in dev/prod — local uses .env.local values directly.
    """
    if settings.is_local:
        return settings

    ssm = boto3.client("ssm", region_name=settings.aws_region)

    param_names = [
        f"{settings.ssm_prefix}/{key}"
        for key in _SSM_PARAM_MAP
    ]

    # Fetch all parameters in one batch call (max 10 per call)
    overrides = {}
    for i in range(0, len(param_names), 10):
        batch = param_names[i:i + 10]
        response = ssm.get_parameters(Names=batch, WithDecryption=True)

        for param in response["Parameters"]:
            # Strip prefix to get the short key
            short_key = param["Name"].removeprefix(f"{settings.ssm_prefix}/")
            field_name = _SSM_PARAM_MAP.get(short_key)
            if field_name:
                overrides[field_name] = param["Value"]

        # Log any parameters that were not found
        for invalid in response.get("InvalidParameters", []):
            print(f"[config] WARNING: Parameter not found in SSM: {invalid}")

    # Return a new Settings instance with SSM values merged in
    return settings.model_copy(update=overrides)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns the application settings. Cached after first call.
    In dev/prod, SSM parameters override .env.local defaults.
    """
    base = Settings()
    return _load_from_ssm(base)


# Module-level singleton for convenience
settings = get_settings()