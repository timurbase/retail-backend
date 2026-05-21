"""
Project-wide pytest config.

Clears DRF's throttle cache between tests so OTP rate limiters don't
leak state across unrelated test functions.
"""

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _reset_throttle_cache():
    cache.clear()
    yield
    cache.clear()
