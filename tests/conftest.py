"""What every test shares: no test reaches another computer.

With no PRICES_KEY, FlipAssist asks the AlertFlip prices API's free UK prices at a real address (flip.prices
.PUBLIC_PRICES_URL), and a price check there can cost that API real credits. Every test of it uses a pretend API, and
this makes sure of it: a test that tries to look up or connect to anything but this computer fails, loudly, before
anything is sent. Ollama on this computer (127.0.0.1) is still allowed."""

import ipaddress
import socket

import pytest

LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


class OffTheNetwork(RuntimeError):
    """A test tried to reach another computer. Not an OSError, so no code under test can take it for a network that's
    down and carry on."""


def local(host):
    """Whether a host is this computer: "localhost", 127.0.0.1, ::1 or none (a name of its own, as a server's bind)."""
    if host is None:
        return True
    host = host.decode() if isinstance(host, bytes) else str(host)
    if host.lower().rstrip(".") in LOCAL_NAMES or host == "":
        return True
    try:
        address = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real_getaddrinfo, real_connect = socket.getaddrinfo, socket.socket.connect

    def getaddrinfo(host, *args, **kwargs):
        if not local(host):
            raise OffTheNetwork(f"a test tried to look up {host}: use a pretend one")
        return real_getaddrinfo(host, *args, **kwargs)

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
            raise OffTheNetwork(f"a test tried to connect to {address[0]}: use a pretend one")
        return real_connect(self, address)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", connect)
