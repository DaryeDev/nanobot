"""Tests for GitHub Copilot provider configuration."""

import pytest

from nanobot.config.schema import Config, ProvidersConfig
from nanobot.providers.registry import find_by_name, find_by_model


def test_github_copilot_in_providers_config():
    """Test that github_copilot field exists in ProvidersConfig."""
    config = ProvidersConfig()
    assert hasattr(config, "github_copilot")
    assert config.github_copilot is not None


def test_github_copilot_provider_spec():
    """Test GitHub Copilot provider spec in registry."""
    spec = find_by_name("github_copilot")
    assert spec is not None
    assert spec.name == "github_copilot"
    assert spec.display_name == "GitHub Copilot"
    assert spec.env_key == "GITHUB_COPILOT_TOKEN"
    assert spec.litellm_prefix == "openai"
    assert spec.default_api_base == "https://api.individual.githubcopilot.com"
    assert "githubcopilot" == spec.detect_by_base_keyword


def test_github_copilot_model_keywords():
    """Test that Copilot models are matched by keywords."""
    # Models with "github-copilot" keyword should match
    spec = find_by_model("github-copilot/something")
    assert spec is not None
    assert spec.name == "github_copilot"
    
    # "copilot" keyword alone should match github_copilot
    spec = find_by_model("copilot")
    assert spec is not None
    assert spec.name == "github_copilot"
    
    # "o3" keyword should match github_copilot
    spec = find_by_model("o3-mini")
    assert spec is not None
    assert spec.name == "github_copilot"


def test_copilot_config_api_key_setting():
    """Test setting GitHub Copilot API key in config."""
    config = Config()
    config.providers.github_copilot.api_key = "ghu_test123"
    assert config.providers.github_copilot.api_key == "ghu_test123"


def test_copilot_config_api_base_setting():
    """Test setting GitHub Copilot API base in config."""
    config = Config()
    config.providers.github_copilot.api_base = "https://api.githubcopilot.com"
    assert config.providers.github_copilot.api_base == "https://api.githubcopilot.com"


def test_get_provider_matches_copilot():
    """Test that get_provider matches GitHub Copilot for copilot models."""
    config = Config()
    config.providers.github_copilot.api_key = "ghu_test123"
    
    provider = config.get_provider("github-copilot/gpt-4o")
    assert provider is not None
    assert provider.api_key == "ghu_test123"
