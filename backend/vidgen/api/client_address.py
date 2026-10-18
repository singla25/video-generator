"""Client address resolution behind trusted proxies (D-15 item 5). Pure functions."""

from __future__ import annotations

from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

Network = IPv4Network | IPv6Network


def parse_networks(values: Sequence[str]) -> tuple[Network, ...]:
    """Turn setting strings (IPs or CIDRs) into networks."""
    return tuple(ip_network(value, strict=False) for value in values)


def _is_trusted(address: str, trusted: Sequence[Network]) -> bool:
    """True if ``address`` is an IP inside one of the trusted networks."""
    try:
        parsed = ip_address(address)
    except ValueError:
        return False
    return any(parsed in network for network in trusted)


def resolve_client_address(peer: str, forwarded_for: str | None, trusted: Sequence[Network]) -> str:
    """The direct peer, unless it is a trusted proxy.

    Then the right-most ``X-Forwarded-For`` entry that is not itself a trusted proxy is the
    client. Any malformed header falls back to the peer, so spoofing cannot split counts.
    """
    if forwarded_for is None or not _is_trusted(peer, trusted):
        return peer
    try:
        chain = [ip_address(part.strip()) for part in forwarded_for.split(",")]
    except ValueError:
        return peer
    untrusted = (str(a) for a in reversed(chain) if not _is_trusted(str(a), trusted))
    return next(untrusted, peer)
