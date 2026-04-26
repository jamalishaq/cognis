from __future__ import annotations

from unittest.mock import patch

from app.providers.notifications.ses import SESNotificationProvider
from app.providers.notifications.slack import SlackNotificationProvider
from app.providers.notifications.teams import TeamsNotificationProvider
from app.registry.notification_registry import get_active_providers


# ---------------------------------------------------------------------------
# Single provider
# ---------------------------------------------------------------------------

@patch("app.registry.notification_registry.settings")
def test_returns_ses_provider_when_configured(mock_settings):
    mock_settings.active_notification_providers = "ses"
    providers = get_active_providers()
    assert len(providers) == 1
    assert isinstance(providers[0], SESNotificationProvider)


@patch("app.registry.notification_registry.settings")
def test_returns_slack_provider_when_configured(mock_settings):
    mock_settings.active_notification_providers = "slack"
    providers = get_active_providers()
    assert len(providers) == 1
    assert isinstance(providers[0], SlackNotificationProvider)


@patch("app.registry.notification_registry.settings")
def test_returns_teams_provider_when_configured(mock_settings):
    mock_settings.active_notification_providers = "teams"
    providers = get_active_providers()
    assert len(providers) == 1
    assert isinstance(providers[0], TeamsNotificationProvider)


# ---------------------------------------------------------------------------
# Multiple providers
# ---------------------------------------------------------------------------

@patch("app.registry.notification_registry.settings")
def test_returns_multiple_providers(mock_settings):
    mock_settings.active_notification_providers = "ses,slack"
    providers = get_active_providers()
    assert len(providers) == 2
    assert isinstance(providers[0], SESNotificationProvider)
    assert isinstance(providers[1], SlackNotificationProvider)


@patch("app.registry.notification_registry.settings")
def test_returns_all_three_providers(mock_settings):
    mock_settings.active_notification_providers = "ses,slack,teams"
    providers = get_active_providers()
    assert len(providers) == 3


@patch("app.registry.notification_registry.settings")
def test_whitespace_around_provider_names_is_ignored(mock_settings):
    mock_settings.active_notification_providers = " ses , slack "
    providers = get_active_providers()
    assert len(providers) == 2
    assert isinstance(providers[0], SESNotificationProvider)
    assert isinstance(providers[1], SlackNotificationProvider)


# ---------------------------------------------------------------------------
# Empty / unknown providers
# ---------------------------------------------------------------------------

@patch("app.registry.notification_registry.settings")
def test_empty_string_returns_no_providers(mock_settings):
    mock_settings.active_notification_providers = ""
    providers = get_active_providers()
    assert providers == []


@patch("app.registry.notification_registry.settings")
def test_unknown_provider_is_skipped(mock_settings):
    mock_settings.active_notification_providers = "pagerduty"
    providers = get_active_providers()
    assert providers == []


@patch("app.registry.notification_registry.settings")
def test_unknown_provider_mixed_with_known_returns_only_known(mock_settings):
    mock_settings.active_notification_providers = "ses,unknown_channel"
    providers = get_active_providers()
    assert len(providers) == 1
    assert isinstance(providers[0], SESNotificationProvider)


@patch("app.registry.notification_registry.settings")
def test_duplicate_provider_names_return_same_instance_twice(mock_settings):
    mock_settings.active_notification_providers = "ses,ses"
    providers = get_active_providers()
    assert len(providers) == 2
    assert all(isinstance(p, SESNotificationProvider) for p in providers)
