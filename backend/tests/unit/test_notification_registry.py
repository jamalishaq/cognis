from __future__ import annotations

from unittest.mock import patch

from app.providers.notifications.ses import SESProvider
from app.providers.notifications.slack import SlackProvider
from app.providers.notifications.teams import TeamsProvider
from app.registry.notification_registry import get_active_providers


@patch("app.registry.notification_registry.settings")
def test_returns_ses_provider_when_configured(mock_settings):
    mock_settings.active_providers_list = ["ses"]
    providers = get_active_providers()
    assert len(providers) == 1
    assert isinstance(providers[0], SESProvider)


@patch("app.registry.notification_registry.settings")
def test_returns_slack_provider_when_configured(mock_settings):
    mock_settings.active_providers_list = ["slack"]
    providers = get_active_providers()
    assert len(providers) == 1
    assert isinstance(providers[0], SlackProvider)


@patch("app.registry.notification_registry.settings")
def test_returns_teams_provider_when_configured(mock_settings):
    mock_settings.active_providers_list = ["teams"]
    providers = get_active_providers()
    assert len(providers) == 1
    assert isinstance(providers[0], TeamsProvider)


@patch("app.registry.notification_registry.settings")
def test_returns_multiple_providers(mock_settings):
    mock_settings.active_providers_list = ["ses", "slack"]
    providers = get_active_providers()
    assert len(providers) == 2
    assert isinstance(providers[0], SESProvider)
    assert isinstance(providers[1], SlackProvider)


@patch("app.registry.notification_registry.settings")
def test_returns_all_three_providers(mock_settings):
    mock_settings.active_providers_list = ["ses", "slack", "teams"]
    providers = get_active_providers()
    assert len(providers) == 3


@patch("app.registry.notification_registry.settings")
def test_empty_list_returns_no_providers(mock_settings):
    mock_settings.active_providers_list = []
    providers = get_active_providers()
    assert providers == []


@patch("app.registry.notification_registry.settings")
def test_unknown_provider_is_skipped(mock_settings):
    mock_settings.active_providers_list = ["pagerduty"]
    providers = get_active_providers()
    assert providers == []


@patch("app.registry.notification_registry.settings")
def test_unknown_provider_mixed_with_known_returns_only_known(mock_settings):
    mock_settings.active_providers_list = ["ses", "unknown_channel"]
    providers = get_active_providers()
    assert len(providers) == 1
    assert isinstance(providers[0], SESProvider)


@patch("app.registry.notification_registry.settings")
def test_duplicate_provider_names_return_same_instance_twice(mock_settings):
    mock_settings.active_providers_list = ["ses", "ses"]
    providers = get_active_providers()
    assert len(providers) == 2
    assert all(isinstance(p, SESProvider) for p in providers)
