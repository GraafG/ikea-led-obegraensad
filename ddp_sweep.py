#!/usr/bin/env python3
"""Sweep a two-column bar across configurable 16x16 panels, left to right."""

import argparse
import sys
import time

from ddp_client import (
    BLACK,
    HEIGHT,
    PIXELS,
    WIDTH,
    DDPWall,
    add_panel_arguments,
    bounded_float,
    bounded_int,
    validate_panels,
)


def sweep(wall, sweeps=2, interval=0.05, brightness=255, flashes=2):
    total_width = WIDTH * len(wall.panels)
    white = bytes([brightness]) * (PIXELS * 3)
    for _ in range(sweeps):
        for x in range(-1, total_width + 1):
            frames = [bytearray(BLACK) for _ in wall.panels]
            for col in (x, x + 1):
                if 0 <= col < total_width:
                    panel, local_x = divmod(col, WIDTH)
                    for y in range(HEIGHT):
                        offset = (y * WIDTH + local_x) * 3
                        frames[panel][offset : offset + 3] = bytes([brightness]) * 3
            wall.send_frames(frames)
            time.sleep(interval)

    for _ in range(flashes):
        wall.send_frames([white] * len(wall.panels))
        time.sleep(0.3)
        wall.clear()
        time.sleep(0.3)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_panel_arguments(parser)
    parser.add_argument("--sweeps", type=bounded_int(1, 100), default=2)
    parser.add_argument(
        "--interval",
        type=bounded_float(0.01, 1),
        default=0.05,
        help="seconds per sweep frame (default: 0.05)",
    )
    parser.add_argument("--brightness", type=bounded_int(5, 255), default=255)
    parser.add_argument(
        "--flashes",
        type=bounded_int(0, 10),
        default=2,
        help="full-wall flashes after sweeping; 0 disables (default: 2)",
    )
    args = parser.parse_args(argv)
    validate_panels(parser, args.panels)
    try:
        with DDPWall(args.panels, args.port) as wall:
            sweep(wall, args.sweeps, args.interval, args.brightness, args.flashes)
    except KeyboardInterrupt:
        print("Interrupted; attempted to clear every panel.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"DDP sweep failed: {exc}", file=sys.stderr)
        return 1
    print("DDP sweep sent; clear sent. UDP delivery is not acknowledged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
