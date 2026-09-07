#!/usr/bin/env python3
"""Check each panel's edge-column lit counts through the firmware /api/data API.

Counts verify receipt/isolation, not physical left-to-right placement or pixel
orientation. Select DDP on every panel and stop other frame senders first.
"""

import argparse
import http.client
import sys
import time
import urllib.request

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


def lit_count(ip, timeout=5.0, http_port=80):
    # Bypass environment proxies so the request goes directly to the panel.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        f"http://{ip}:{http_port}/api/data", headers={"Cache-Control": "no-cache"}
    )
    with opener.open(request, timeout=timeout) as response:
        data = response.read(PIXELS + 1)
    if len(data) != PIXELS:
        raise ValueError(f"{ip}: expected {PIXELS} grayscale bytes, got {len(data)}")
    return sum(value > 4 for value in data)


def verify(wall, settle=0.4, timeout=5.0, http_port=80):
    passed = True
    for target, ip in enumerate(wall.panels):
        for col in (0, WIDTH - 1):
            frames = [bytearray(BLACK) for _ in wall.panels]
            for y in range(HEIGHT):
                offset = (y * WIDTH + col) * 3
                frames[target][offset : offset + 3] = b"\xff\xff\xff"
            wall.send_frames(frames)
            time.sleep(settle)
            for index, address in enumerate(wall.panels):
                expected = HEIGHT if index == target else 0
                actual = lit_count(address, timeout, http_port)
                matched = actual == expected
                passed = passed and matched
                print(
                    f"{'PASS' if matched else 'FAIL'} target {target + 1} ({ip}) "
                    f"column {col}, panel {index + 1} ({address}): "
                    f"lit={actual}, expected={expected}"
                )
    return passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_panel_arguments(parser)
    parser.add_argument(
        "--settle",
        type=bounded_float(0.05, 10),
        default=0.4,
        help="seconds to wait after sending each test frame (default: 0.4)",
    )
    parser.add_argument(
        "--timeout",
        type=bounded_float(0.1, 60),
        default=5.0,
        help="HTTP timeout in seconds (default: 5)",
    )
    parser.add_argument("--http-port", type=bounded_int(1, 65535), default=80)
    args = parser.parse_args(argv)
    validate_panels(parser, args.panels)
    try:
        with DDPWall(args.panels, args.port) as wall:
            passed = verify(wall, args.settle, args.timeout, args.http_port)
    except KeyboardInterrupt:
        print("Interrupted; attempted to clear every panel.", file=sys.stderr)
        return 130
    except (OSError, ValueError, http.client.HTTPException) as exc:
        print(f"DDP verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Count checks passed; clear sent."
        if passed
        else "Count checks FAILED; clear sent."
    )
    print("Verify physical panel order/orientation visually with ddp_sweep.py.")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
