"""Tests may use HTTP mock transports, never a running model or cloud service."""

import httpx
import pytest


@pytest.fixture(autouse=True)
def block_unmocked_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Use an HTTP mock transport; tests must not invoke real models.')

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', blocked)

    async def async_blocked(*args, **kwargs):
        blocked()

    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', async_blocked)
