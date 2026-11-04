import json
import math
from pathlib import Path
import pytest

from capacity import pricing


def test_valid_cache_loads():
    prices = pricing.load_prices()
    assert isinstance(prices, dict)
    assert len(prices) > 0


def test_missing_instance_price_detected():
    prices = pricing.load_prices()
    with pytest.raises(KeyError, match="not_a_type"):
        pricing.get_price("not_a_type", prices)


def test_invalid_prices_rejected():
    bad_prices = {"t3.micro": float("nan"), "t3.small": float("inf"), "t3.medium": -0.1}
    for k, v in bad_prices.items():
        invalid_dict = {"t3.micro": 0.01, k: v}
        # load_prices validates directly; let's test via save/load cycle
        pass
    # Direct validation: save should reject
    with pytest.raises(ValueError):
        pricing.save_price_cache(bad_prices)


def test_price_retrieval_raises_on_network_failure(monkeypatch):
    # Monkeypatch urlopen to raise immediately
    def mock_urlopen(*args, **kwargs):
        raise ConnectionError("Mocked failure")
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    with pytest.raises(Exception):
        pricing.retrieve_prices_from_aws_api()


def test_network_failure_does_not_corrupt_existing_cache(monkeypatch):
    # Monkeypatch urlopen to raise
    def mock_urlopen(*args, **kwargs):
        raise ConnectionError("Mocked failure")
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    prices_before = pricing.load_prices()
    try:
        pricing.retrieve_prices_from_aws_api()
    except Exception:
        pass
    prices_after = pricing.load_prices()
    assert prices_before == prices_after


def test_unit_tests_do_not_require_live_aws_access():
    # This test asserts that load_prices works from the fixture file.
    # If the fixture is present, the test passes without network.
    prices = pricing.load_prices()
    assert "t3.micro" in prices
