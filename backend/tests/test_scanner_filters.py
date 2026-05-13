"""Tests for the relay's scanner subnet-detection + result filters.

These tests exercise the pure-Python helpers; they do not require the
relay to be running.
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, "/app/ais_push_relay")
import scanner  # noqa: E402


# --- Subnet eligibility ---------------------------------------------------

def test_loopback_iface_is_not_eligible():
    flags = scanner._classify_iface("lo")
    assert flags["is_loopback"] is True
    assert flags["is_docker"] is False


def test_docker_iface_prefixes_classified_as_docker():
    for name in ("docker0", "br-abc123", "veth1234", "cni0", "flannel.1", "tun0", "vxlan.calico"):
        flags = scanner._classify_iface(name)
        assert flags["is_docker"], f"{name} should be docker-classified"


def test_regular_iface_not_flagged():
    for name in ("eth0", "ens33", "enp4s0", "wlp2s0", "wlan0"):
        flags = scanner._classify_iface(name)
        assert not flags["is_docker"], f"{name} should not be docker-classified"
        assert not flags["is_loopback"]


def test_classify_ip_buckets():
    assert scanner._classify_ip("127.0.0.1")["is_loopback"] is True
    assert scanner._classify_ip("169.254.1.5")["is_link_local"] is True
    assert scanner._classify_ip("192.168.1.42")["is_private"] is True
    assert scanner._classify_ip("10.0.0.1")["is_private"] is True
    assert scanner._classify_ip("172.17.0.1")["is_172_block"] is True
    assert scanner._classify_ip("224.0.0.1")["is_reserved"] is True


def test_resolve_targets_explicit_subnet():
    targets, label = scanner.resolve_targets("192.168.99.0/30", [7000])
    assert label == "192.168.99.0/30"
    # /30 has 2 usable hosts
    assert len(targets) == 2
    assert all(p == 7000 for _, p in targets)


def test_resolve_targets_rejects_ipv6():
    with pytest.raises(ValueError):
        scanner.resolve_targets("fe80::/64", None)


def test_resolve_targets_rejects_bad_input():
    with pytest.raises(ValueError):
        scanner.resolve_targets("not-a-cidr", None)


def test_resolve_targets_no_auto_subnet_raises_clear_error(monkeypatch):
    """When auto-detect finds nothing, raise NoUsableSubnetError with the spec message."""
    monkeypatch.setattr(scanner, "detect_local_subnets", lambda: [])
    with pytest.raises(scanner.NoUsableSubnetError) as exc_info:
        scanner.resolve_targets(None, [7000])
    msg = str(exc_info.value)
    assert "No scannable LAN subnet found from this relay" in msg
    assert "subnet manually" in msg


# --- Result filtering ------------------------------------------------------

@pytest.fixture
def candidates():
    return [
        {"ip": "127.0.0.1", "port": 5353, "status": "socket_open", "score": 25,
         "sample": None, "details": {"is_ais": False, "is_nmea": False}},
        {"ip": "172.17.0.5", "port": 7000, "status": "socket_open", "score": 25,
         "sample": None, "details": {"is_ais": False, "is_nmea": False}},
        {"ip": "172.18.0.2", "port": 5353, "status": "data_received", "score": 45,
         "sample": "hello", "details": {"is_ais": False, "is_nmea": False}},
        {"ip": "169.254.10.1", "port": 7000, "status": "socket_open", "score": 25,
         "sample": None, "details": {}},
        {"ip": "192.168.1.42", "port": 7000, "status": "ais_detected", "score": 90,
         "sample": "!AIVDM,1,1,,A,15RTgt...,0*4A",
         "details": {"is_ais": True, "is_nmea": False}},
        {"ip": "192.168.1.55", "port": 5353, "status": "data_received", "score": 45,
         "sample": "something",
         "details": {"is_ais": False, "is_nmea": False}},
        {"ip": "192.168.1.99", "port": 10110, "status": "socket_open", "score": 25,
         "sample": None,
         "details": {"is_ais": False, "is_nmea": False}},
    ]


def test_default_filter_excludes_loopback_docker_and_low_conf(candidates):
    out = scanner.filter_results(candidates)
    ips = {c["ip"] for c in out}
    # Default keeps only LAN IPs with AIS/NMEA/sample
    assert ips == {"192.168.1.42", "192.168.1.55"}


def test_default_filter_excludes_link_local(candidates):
    out = scanner.filter_results(candidates)
    assert not any(c["ip"].startswith("169.254.") for c in out)


def test_include_low_confidence_adds_socket_open_results(candidates):
    out = scanner.filter_results(candidates, include_low_confidence=True)
    ips = {c["ip"] for c in out}
    # Now the 192.168.1.99 socket_open row is included
    assert "192.168.1.99" in ips
    # But docker + loopback still excluded
    assert "127.0.0.1" not in ips
    assert "172.17.0.5" not in ips
    assert "172.18.0.2" not in ips


def test_keep_docker_when_explicitly_requested(candidates):
    out = scanner.filter_results(
        candidates, exclude_docker=False, exclude_loopback=False, include_low_confidence=True
    )
    ips = {c["ip"] for c in out}
    assert "127.0.0.1" in ips
    assert "172.17.0.5" in ips
    assert "172.18.0.2" in ips


def test_sample_classifier_distinguishes_ais_nmea_garbage():
    assert scanner._classify_sample(b"!AIVDM,1,1,,A,15...,0*4A\r\n")["is_ais"] is True
    assert scanner._classify_sample(b"$GPRMC,123519,A,4807.038,N,...*6A\r\n")["is_nmea"] is True
    assert scanner._classify_sample(b"random http server hello")["is_ais"] is False
    assert scanner._classify_sample(b"random http server hello")["is_nmea"] is False
