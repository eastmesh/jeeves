"""CLI argument parsing and application bootstrap."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meshcore-pathbot",
        description="MeshCore Path Resolver Bot with Web Dashboard",
    )

    parser.add_argument(
        "--config", "-C",
        type=Path,
        default=None,
        help="Path to TOML config file",
    )

    # Connection options
    conn = parser.add_mutually_exclusive_group()
    conn.add_argument("-s", "--serial", help="Serial port (e.g. /dev/ttyUSB0, COM3)")
    conn.add_argument("-t", "--tcp", help="TCP host (e.g. 192.168.1.100)")
    conn.add_argument(
        "-b", "--ble",
        help="BLE address (or empty to scan)",
        nargs="?",
        const="",
    )

    parser.add_argument("-p", "--port", type=int, default=None, help="TCP port (default: 5000)")
    parser.add_argument("-B", "--baud", type=int, default=None, help="Serial baud rate")
    parser.add_argument(
        "-c", "--channel",
        type=int,
        default=None,
        help="Channel to listen on",
    )
    parser.add_argument(
        "-r", "--repeaters-file",
        type=Path,
        default=None,
        help="Repeaters DB path (.db preferred; .json auto-migrates)",
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "-i", "--ignore",
        nargs="*",
        default=[],
        help="Additional node names to ignore",
    )

    # Web options
    parser.add_argument("--web-host", default=None, help="Web dashboard bind host")
    parser.add_argument("--web-port", type=int, default=None, help="Web dashboard port")
    parser.add_argument("--no-web", action="store_true", help="Disable web dashboard")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    from .config.loader import load_config

    config = load_config(args.config, args)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    from .app import run

    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        pass
