"""Shared, standard-library-only transport for the 16x16 DDP wall tools."""

import argparse
import ipaddress
import math
import socket
import struct
import sys

WIDTH = HEIGHT = 16
PIXELS = WIDTH * HEIGHT
PAYLOAD_SIZE = PIXELS * 3
BLACK = bytes(PAYLOAD_SIZE)


def bounded_int(low, high):
    def parse(value):
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("must be an integer") from exc
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number

    return parse


def bounded_float(low, high):
    def parse(value):
        try:
            number = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("must be a number") from exc
        if not math.isfinite(number) or not low <= number <= high:
            raise argparse.ArgumentTypeError(
                f"must be finite and between {low} and {high}"
            )
        return number

    return parse


def panel_ip(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise argparse.ArgumentTypeError("must be an IPv4 address") from exc
    if (
        address.is_unspecified
        or address.is_multicast
        or str(address) == "255.255.255.255"
    ):
        raise argparse.ArgumentTypeError("must be a unicast panel address")
    return str(address)


def add_panel_arguments(parser):
    parser.add_argument(
        "--panels",
        nargs="+",
        required=True,
        type=panel_ip,
        metavar="IP",
        help="1-64 panel IPv4 addresses, in physical LEFT-to-RIGHT order (no defaults)",
    )
    parser.add_argument(
        "--port",
        type=bounded_int(1, 65535),
        default=4048,
        help="DDP UDP port (default: 4048)",
    )


def validate_panels(parser, panels):
    if not 1 <= len(panels) <= 64:
        parser.error("--panels requires 1-64 addresses")
    if len(set(panels)) != len(panels):
        parser.error("--panels must not contain duplicate addresses")


def create_packet(payload):
    """One full RGB24 frame, DDP v1/PUSH, display ID 1, offset 0.

    Sequence 0 disables sequencing. The firmware consumes row-major RGB
    triples after this ten-byte header and averages them to grayscale.
    """
    if not isinstance(payload, (bytes, bytearray)) or len(payload) != PAYLOAD_SIZE:
        raise ValueError(
            f"each panel requires exactly {PAYLOAD_SIZE} RGB payload bytes"
        )
    return struct.pack(">BBBBIH", 0x41, 0, 1, 1, 0, len(payload)) + payload


class DDPWall:
    """Own one UDP socket; attempt to clear every panel on every exit path."""

    def __init__(self, panels, port=4048):
        self.panels = tuple(panels)
        self.port = port
        self.sock = None

    def __enter__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.settimeout(2.0)
        except OSError:
            self.sock.close()
            self.sock = None
            raise
        return self

    def send(self, ip, payload):
        if self.sock is None:
            raise RuntimeError("DDPWall must be used as a context manager")
        packet = create_packet(payload)
        sent = self.sock.sendto(packet, (ip, self.port))
        if sent != len(packet):
            raise OSError(f"short UDP send to {ip}: {sent}/{len(packet)} bytes")

    def send_frames(self, frames):
        if len(frames) != len(self.panels):
            raise ValueError("frame count must match panel count")
        for ip, frame in zip(self.panels, frames):
            self.send(ip, frame)

    def clear(self):
        first_error = None
        for ip in self.panels:
            try:
                self.send(ip, BLACK)
            except OSError as exc:
                print(f"Unable to clear panel {ip}: {exc}", file=sys.stderr)
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            try:
                self.clear()
            except OSError:
                # clear() reports each failure; preserve any original exception.
                if exc_type is None:
                    raise
        finally:
            self.sock.close()
            self.sock = None
        return False
