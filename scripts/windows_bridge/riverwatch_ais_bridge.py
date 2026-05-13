"""River Watch AIS Bridge - Windows-friendly launcher.

Wraps ``scripts/ais_relay.py`` so non-technical users can drop a single .exe
on a laptop / mini-PC that is on the same LAN as Boat Beacon and have AIS
data flow to the River Watch GCP collector with zero CLI knowledge.

Behaviour:
  * Reads ``riverwatch_bridge.ini`` from the same folder as the executable.
  * Falls back to a built-in default config if the INI is missing
    (writes a template next to the .exe so the user can edit it).
  * Translates that config into the environment variables that
    ``scripts/ais_relay.py`` already understands, then drives the proven
    discovery + relay loop from that module.
  * Prints a clean status line ("Lines relayed: 12  Last data: ...")
    every few seconds so the user can confirm activity at a glance.
  * Supports a tiny CLI: ``--status`` (one-shot health check),
    ``--clear-cache`` (forget cached Boat Beacon feed),
    ``install-service`` / ``uninstall-service`` / ``start-service`` /
    ``stop-service`` (delegated to NSSM - see README).

The script is single-file and pure stdlib (configparser, logging, socket,
threading), which keeps PyInstaller output small and predictable.
"""

from __future__ import annotations

import argparse
import configparser
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "RiverWatchAISBridge"
SERVICE_NAME = "RiverWatchAISBridge"
DEFAULT_CONFIG_NAME = "riverwatch_bridge.ini"

DEFAULT_CONFIG = {
    "collector": {
        "ip": "34.172.47.153",
        "port": "6000",
        "token": "",
    },
    "boat_beacon": {
        # When set, skip auto-discovery and connect directly:
        "ip": "",
        "port": "",
        # Force a specific subnet to scan (e.g. 192.168.0.0/24).
        "subnet": "",
        # Cache file path (empty = default: ~/.riverwatch_ais_relay.json)
        "cache_path": "",
    },
    "logging": {
        # one of: DEBUG, INFO, WARNING, ERROR
        "level": "INFO",
        # Status line every N seconds. 0 to disable.
        "status_interval_seconds": "10",
        # Append all log lines to a rolling file in this folder. Empty = console only.
        "log_dir": "",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bundle_dir() -> Path:
    """Folder where the .exe / .py lives - where the config and cache should sit."""
    if getattr(sys, "frozen", False):
        # PyInstaller one-file build: sys.executable points at the exe.
        return Path(sys.executable).parent.resolve()
    return Path(__file__).resolve().parent


def _default_config_path() -> Path:
    return _bundle_dir() / DEFAULT_CONFIG_NAME


def _write_template_config(path: Path) -> None:
    """Write a commented INI template to ``path`` so users have something to edit."""
    template = """# River Watch AIS Bridge configuration
# Lines starting with ; or # are comments.
# Save changes and restart the bridge for them to take effect.

[collector]
# River Watch GCP collector IP and port. Defaults match the current test rig.
ip   = 34.172.47.153
port = 6000
# Optional shared secret - leave blank unless ops told you otherwise.
token =

[boat_beacon]
# Leave ip/port blank to auto-discover Boat Beacon on the local network.
# Fill them in if you already know them (skips the LAN scan).
ip   =
port =
# Force a specific subnet to scan, e.g. 192.168.0.0/24. Blank = auto.
subnet =
# Override cache file location. Blank = %USERPROFILE%\\.riverwatch_ais_relay.json
cache_path =

[logging]
# Console verbosity: DEBUG, INFO, WARNING, ERROR
level = INFO
# Print a "Lines relayed: ..." summary every N seconds. 0 to disable.
status_interval_seconds = 10
# Empty = console only. Otherwise the bridge writes daily logs into this folder.
log_dir =
"""
    path.write_text(template, encoding="utf-8")


def _load_config(path: Path, logger: logging.Logger) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read_dict(DEFAULT_CONFIG)
    if not path.exists():
        logger.info("Config file not found - writing template to %s", path)
        try:
            _write_template_config(path)
        except OSError as e:
            logger.warning("Could not write template config: %s", e)
        return cfg
    try:
        cfg.read(path, encoding="utf-8")
        logger.info("Loaded config from %s", path)
    except (configparser.Error, OSError) as e:
        logger.error("Failed to read %s: %s. Using defaults.", path, e)
    return cfg


def _setup_logging(level_name: str, log_dir: str) -> logging.Logger:
    level = getattr(logging, level_name.upper(), logging.INFO)
    handlers: list = [logging.StreamHandler(stream=sys.stdout)]
    if log_dir:
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            fname = time.strftime(f"{APP_NAME}-%Y%m%d.log")
            handlers.append(logging.FileHandler(Path(log_dir) / fname, encoding="utf-8"))
        except OSError as e:
            print(f"WARNING: Could not write log_dir {log_dir}: {e}", flush=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(APP_NAME)


def _apply_config_to_env(cfg: configparser.ConfigParser) -> None:
    """Translate the INI values into the env vars used by scripts/ais_relay.py."""
    coll_ip = cfg.get("collector", "ip", fallback="").strip()
    coll_port = cfg.get("collector", "port", fallback="").strip()
    token = cfg.get("collector", "token", fallback="").strip()
    bb_ip = cfg.get("boat_beacon", "ip", fallback="").strip()
    bb_port = cfg.get("boat_beacon", "port", fallback="").strip()
    bb_subnet = cfg.get("boat_beacon", "subnet", fallback="").strip()
    cache_path = cfg.get("boat_beacon", "cache_path", fallback="").strip()

    if coll_ip:
        os.environ["COLLECTOR_IP"] = coll_ip
    if coll_port:
        os.environ["COLLECTOR_PORT"] = coll_port
    if token:
        os.environ["RELAY_TOKEN"] = token
    if bb_ip:
        os.environ["BOAT_BEACON_IP"] = bb_ip
    if bb_port:
        os.environ["BOAT_BEACON_PORT"] = bb_port
    if bb_subnet:
        os.environ["BOAT_BEACON_SUBNET"] = bb_subnet
    if cache_path:
        os.environ["AIS_RELAY_CACHE"] = cache_path


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_file(cfg: configparser.ConfigParser) -> Path:
    override = cfg.get("boat_beacon", "cache_path", fallback="").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".riverwatch_ais_relay.json"


def cmd_clear_cache(cfg: configparser.ConfigParser, logger: logging.Logger) -> int:
    path = _cache_file(cfg)
    if path.exists():
        try:
            path.unlink()
            logger.info("Removed cached Boat Beacon feed: %s", path)
            return 0
        except OSError as e:
            logger.error("Failed to delete cache %s: %s", path, e)
            return 1
    logger.info("No cache file to remove (%s)", path)
    return 0


def cmd_status(cfg: configparser.ConfigParser, logger: logging.Logger) -> int:
    """One-shot health check: cache state + collector reachability."""
    cache = _cache_file(cfg)
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            logger.info(
                "Cached Boat Beacon feed: %s:%s (selected %s, source=%s)",
                data.get("ip"), data.get("port"),
                data.get("selected_at"), data.get("source"),
            )
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Cache file unreadable: %s", e)
    else:
        logger.info("No cached Boat Beacon feed yet (%s)", cache)

    coll_ip = cfg.get("collector", "ip", fallback="34.172.47.153")
    coll_port = int(cfg.get("collector", "port", fallback="6000"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((coll_ip, coll_port))
        logger.info("Collector %s:%s reachable - OK", coll_ip, coll_port)
        result = 0
    except OSError as e:
        logger.error("Collector %s:%s unreachable: %s", coll_ip, coll_port, e)
        result = 2
    finally:
        sock.close()
    return result


# ---------------------------------------------------------------------------
# Periodic status printer
# ---------------------------------------------------------------------------

def _status_printer(stats: dict, interval: int, logger: logging.Logger) -> threading.Thread:
    def _run() -> None:
        while True:
            time.sleep(interval)
            last = stats.get("last_data_time")
            last_str = last.strftime("%H:%M:%S") if last else "n/a"
            logger.info(
                "STATUS lines=%s bytes=%s errors=%s last_data=%s",
                stats.get("lines_relayed", 0),
                stats.get("bytes_relayed", 0),
                stats.get("errors", 0),
                last_str,
            )

    t = threading.Thread(target=_run, name="status-printer", daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Service commands (delegated to NSSM if present)
# ---------------------------------------------------------------------------

def _find_nssm() -> Optional[str]:
    here = _bundle_dir() / "nssm.exe"
    if here.exists():
        return str(here)
    return shutil.which("nssm") or shutil.which("nssm.exe")


def _run_nssm(args: list, logger: logging.Logger) -> int:
    nssm = _find_nssm()
    if not nssm:
        logger.error(
            "NSSM not found. Install it (https://nssm.cc/) and either add it to PATH "
            "or copy nssm.exe next to %s.exe. See README for the full walkthrough.",
            APP_NAME,
        )
        return 4
    cmd = [nssm] + args
    logger.info("Running: %s", " ".join(cmd))
    try:
        res = subprocess.run(cmd, check=False)
        return res.returncode
    except OSError as e:
        logger.error("NSSM invocation failed: %s", e)
        return 5


def cmd_install_service(cfg_path: Path, logger: logging.Logger) -> int:
    exe = sys.executable if getattr(sys, "frozen", False) else sys.argv[0]
    return _run_nssm([
        "install", SERVICE_NAME, exe, "--config", str(cfg_path),
    ], logger)


def cmd_uninstall_service(logger: logging.Logger) -> int:
    return _run_nssm(["remove", SERVICE_NAME, "confirm"], logger)


def cmd_start_service(logger: logging.Logger) -> int:
    return _run_nssm(["start", SERVICE_NAME], logger)


def cmd_stop_service(logger: logging.Logger) -> int:
    return _run_nssm(["stop", SERVICE_NAME], logger)


# ---------------------------------------------------------------------------
# Main relay (delegates to scripts/ais_relay.py)
# ---------------------------------------------------------------------------

def run_relay(cfg: configparser.ConfigParser, logger: logging.Logger) -> int:
    _apply_config_to_env(cfg)

    # Import AFTER env vars are set - the module reads them at import time.
    # Ensure the parent scripts/ folder is on sys.path so the import works
    # both in dev (running this file directly) and inside the PyInstaller bundle.
    scripts_dir = Path(__file__).resolve().parent.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        import ais_relay  # type: ignore  # local script, not packaged
    except ImportError as e:
        logger.error("Failed to import bundled ais_relay module: %s", e)
        return 10

    logger.info("=" * 56)
    logger.info("River Watch AIS Bridge starting")
    logger.info("Collector: %s:%s", ais_relay.COLLECTOR_IP, ais_relay.COLLECTOR_PORT)
    logger.info("Cache file: %s", ais_relay.CACHE_PATH)
    if ais_relay.BOAT_BEACON_IP and ais_relay.BOAT_BEACON_PORT:
        logger.info("Boat Beacon: %s:%s (forced)",
                    ais_relay.BOAT_BEACON_IP, ais_relay.BOAT_BEACON_PORT)
    else:
        logger.info("Boat Beacon: auto-discover")
    logger.info("=" * 56)

    # Optional periodic status line.
    try:
        interval = int(cfg.get("logging", "status_interval_seconds", fallback="10"))
    except ValueError:
        interval = 10
    if interval > 0:
        _status_printer(ais_relay.stats, interval, logger)

    feed = ais_relay.determine_boat_beacon()
    if not feed:
        logger.error(
            "No Boat Beacon AIS feed found. Confirm Boat Beacon TCP output is enabled "
            "and this PC is on the same Wi-Fi/Ethernet as the Boat Beacon device. "
            "See README -> Troubleshooting."
        )
        return 11

    try:
        ais_relay.relay_loop(feed)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        ais_relay.print_stats()
        logger.info("Bridge stopped.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=APP_NAME,
        description="River Watch AIS Bridge - forwards Boat Beacon AIS to the GCP collector.",
    )
    p.add_argument("--config", "-c", help="Path to riverwatch_bridge.ini (default: next to .exe)")
    p.add_argument("--status", action="store_true", help="Print current state and collector reachability, then exit.")
    p.add_argument("--clear-cache", action="store_true", help="Forget the cached Boat Beacon feed and exit.")
    p.add_argument("command", nargs="?", choices=[
        "run", "install-service", "uninstall-service", "start-service", "stop-service",
    ], default="run", help="Subcommand. Defaults to 'run'.")
    return p


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve() if args.config else _default_config_path()

    # Bootstrap logging at INFO so messages during config load are visible.
    boot_logger = _setup_logging("INFO", "")
    cfg = _load_config(config_path, boot_logger)

    level = cfg.get("logging", "level", fallback="INFO")
    log_dir = cfg.get("logging", "log_dir", fallback="")
    logger = _setup_logging(level, log_dir)

    if args.status:
        return cmd_status(cfg, logger)
    if args.clear_cache:
        return cmd_clear_cache(cfg, logger)

    if args.command == "install-service":
        return cmd_install_service(config_path, logger)
    if args.command == "uninstall-service":
        return cmd_uninstall_service(logger)
    if args.command == "start-service":
        return cmd_start_service(logger)
    if args.command == "stop-service":
        return cmd_stop_service(logger)

    return run_relay(cfg, logger)


if __name__ == "__main__":
    sys.exit(main())
