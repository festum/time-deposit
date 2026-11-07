from __future__ import annotations

import pytest

import postgres


@pytest.fixture(scope='session', autouse=True)
def _close_connection_pools():
    yield
    postgres.POOLS.close_all()
