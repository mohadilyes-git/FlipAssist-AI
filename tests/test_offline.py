"""The tests never reach another computer (tests/conftest.py): an address can't be looked up or connected to, so a test
that forgets its pretend prices API fails before anything is sent. This computer's own addresses still work."""

import socket
import urllib.request

import pytest


def test_another_computer_is_never_looked_up_or_connected_to():
    with pytest.raises(RuntimeError, match="a test tried to look up prices.invalid"):
        socket.getaddrinfo("prices.invalid", 443)
    with pytest.raises(RuntimeError, match="a test tried to look up prices.invalid"):
        urllib.request.urlopen("https://prices.invalid/functions/v1/prices-", timeout=1)
    with socket.socket() as plain, pytest.raises(RuntimeError, match="a test tried to connect to 192.0.2.1"):
        plain.connect(("192.0.2.1", 443))  # an address kept for examples, never routed


def test_this_computer_is_still_reachable():
    from conftest import local
    assert all(local(host) for host in ("localhost", "127.0.0.1", "::1", "0.0.0.0", None))
    assert not any(local(host) for host in ("example.com", "kgwykdmpcmvtyjnmlnqk.supabase.co", "192.0.2.1", "8.8.8.8"))
