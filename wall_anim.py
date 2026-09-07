#!/usr/bin/env python3
"""Grayscale animations across 16x16 DDP panels in CLI left-to-right order.

Duration includes intros and transitions; all plays each standalone animation
once, excluding the composite loop. No network activity occurs on import.
"""

import sys
import time
import math
import argparse

from ddp_client import (
    HEIGHT,
    WIDTH,
    DDPWall,
    add_panel_arguments,
    bounded_float,
    bounded_int,
    validate_panels,
)

PW, PH = WIDTH, HEIGHT
WW, WH = PW, PH
_wall = None

# grayscale -> RGB triple lookup, so payload building is a fast join
_TRIP = [bytes((v, v, v)) for v in range(256)]


class Ticker:
    """Absolute-deadline pacer: keeps a steady fps regardless of per-frame
    compute time, and skips sleeping (but stays aligned) if we fall behind."""

    def __init__(self, fps, duration):
        self.dt = 1.0 / fps
        self.next_t = time.perf_counter()
        self.deadline = self.next_t + duration

    @property
    def expired(self):
        return time.perf_counter() >= self.deadline

    def frames(self, count):
        for index in range(count):
            if self.expired:
                break
            yield index

    def wait(self):
        self.next_t += self.dt
        delay = min(self.next_t, self.deadline) - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
            return delay
        else:
            # we're behind; realign so we don't spiral
            self.next_t = time.perf_counter()
            return delay


class Canvas:
    """Wall-sized grayscale canvas; brightness 0-255."""

    def __init__(self):
        self.buf = [0] * (WW * WH)

    def clear(self):
        self.buf = [0] * (WW * WH)

    def set(self, x, y, b):
        if 0 <= x < WW and 0 <= y < WH:
            xi = int(x)
            yi = int(y)
            if b > self.buf[yi * WW + xi]:
                self.buf[yi * WW + xi] = min(255, int(b))

    def push(self):
        if _wall is None:
            raise RuntimeError("configure a DDPWall before playing animations")
        buf = self.buf
        for p, ip in enumerate(_wall.panels):
            payload = bytearray()
            x0 = p * PW
            for y in range(PH):
                row = (y * WW) + x0
                payload += b"".join([_TRIP[buf[row + x]] for x in range(PW)])
            _wall.send(ip, payload)


def clear_all():
    if _wall is None:
        raise RuntimeError("configure a DDPWall before playing animations")
    _wall.clear()


def configure(wall):
    """Attach an open transport; panel count determines the canvas width."""
    global _wall, WW
    _wall = wall
    WW = PW * len(wall.panels)


# ---------------------------------------------------------------- radar
def radar(duration=20.0, fps=60):
    cx, cy = WW / 2.0, WH / 2.0
    max_r = WW / 2.0  # sweep reaches the outer panels
    # a few static "targets"
    import random

    blips = [(random.randint(0, WW - 1), random.randint(0, WH - 1)) for _ in range(7)]
    trail = [0] * (WW * WH)  # persistent fade buffer
    angle = 0.0
    speed = 2.8 / fps  # ~2.8 rad/s regardless of fps
    frames = max(1, math.ceil(duration * fps))
    tick = Ticker(fps, duration)
    for _ in tick.frames(frames):
        # fade the trail
        for i in range(len(trail)):
            trail[i] = trail[i] - 14 if trail[i] > 14 else 0

        c = Canvas()

        # range rings (ellipse to fit the short height)
        for rr in range(4, int(max_r), 5):
            steps = max(24, int(rr * 4))
            for s in range(steps):
                a = (2 * math.pi * s) / steps
                x = cx + math.cos(a) * rr
                y = cy + math.sin(a) * (rr * WH / WW)
                c.set(x, y, 26)

        # sweep beam with a short angular tail
        for k in range(6):
            a = angle - k * 0.10
            b = 255 - k * 38
            for r in range(int(max_r)):
                x = cx + math.cos(a) * r
                y = cy + math.sin(a) * (r * WH / WW)
                if 0 <= x < WW and 0 <= y < WH:
                    idx = int(y) * WW + int(x)
                    val = max(b - r * 4, 40)
                    if val > trail[idx]:
                        trail[idx] = val

        # blips light up when the beam passes over them
        for bx, by in blips:
            dx, dy = bx - cx, (by - cy) * WW / WH
            ba = math.atan2(dy, dx)
            diff = abs((angle - ba + math.pi) % (2 * math.pi) - math.pi)
            if diff < 0.18:
                idx = by * WW + bx
                trail[idx] = 255

        # merge trail into canvas
        for y in range(WH):
            for x in range(WW):
                v = trail[y * WW + x]
                if v:
                    c.set(x, y, v)

        c.push()
        angle = (angle + speed) % (2 * math.pi)
        tick.wait()
    clear_all()


# ---------------------------------------------------------------- wave
def wave(duration=15.0, fps=60):
    frames = max(1, math.ceil(duration * fps))
    t = 0.0
    t_step = 6.25 / fps  # ~constant wave speed regardless of fps
    tick = Ticker(fps, duration)
    for _ in tick.frames(frames):
        c = Canvas()
        for x in range(WW):
            y = (
                WH / 2
                + math.sin((x / 5.0) + t) * (WH / 2 - 1)
                + math.sin((x / 11.0) - t * 0.7) * 2
            )
            for yy in range(WH):
                d = abs(yy - y)
                if d < 2.2:
                    c.set(x, yy, int(255 * (1 - d / 2.2)))
        c.push()
        t += t_step
        tick.wait()
    clear_all()


# ---------------------------------------------------------------- marquee
FONT = {
    " ": ["000", "000", "000", "000", "000"],
    "!": ["010", "010", "010", "000", "010"],
    "A": ["010", "101", "111", "101", "101"],
    "B": ["110", "101", "110", "101", "110"],
    "C": ["011", "100", "100", "100", "011"],
    "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"],
    "G": ["011", "100", "101", "101", "011"],
    "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"],
    "M": ["101", "111", "111", "101", "101"],
    "O": ["111", "101", "101", "101", "111"],
    "R": ["110", "101", "110", "101", "101"],
    "V": ["101", "101", "101", "101", "010"],
}
_FONT_BIG = FONT


def marquee(text="HI OBE!", duration=12.0, fps=60):
    text = text.upper()
    glyph_w = 4  # 3 + 1 space
    total = len(text) * glyph_w
    frames = max(1, math.ceil(duration * fps))
    pps = 20.0  # scroll speed in px/sec, fps-independent
    tick = Ticker(fps, duration)
    for f in tick.frames(frames):
        offset = int(f * pps / fps) % (total + WW) - WW
        c = Canvas()
        for i, ch in enumerate(text):
            g = FONT.get(ch, FONT[" "])
            gx = i * glyph_w - offset
            for ry in range(5):
                for rx in range(3):
                    if g[ry][rx] == "1":
                        c.set(gx + rx, 6 + ry, 255)
        c.push()
        tick.wait()
    clear_all()


# ---------------------------------------------------------------- matrix rain
def matrix(duration=20.0, fps=60):
    import random

    frames = max(1, math.ceil(duration * fps))
    fade = [0] * (WW * WH)  # persistent brightness buffer
    max_trail = 9
    # fall speeds in px/frame, scaled so motion looks the same at any fps
    smin, smax = 12.0 / fps, 34.0 / fps

    class Drop:
        __slots__ = ("y", "speed", "length", "active")

        def __init__(self):
            self.y = -random.uniform(0, WH)
            self.speed = random.uniform(smin, smax)
            self.length = random.randint(3, max_trail)
            self.active = random.random() > 0.3

    cols = [Drop() for _ in range(WW)]

    fade_step = max(4, int(300 / fps))  # ~constant fade per second
    spawn_p = 1.0 / fps  # ~1 respawn/sec per idle column
    tick = Ticker(fps, duration)
    for _ in tick.frames(frames):
        # fade everything
        for i in range(len(fade)):
            fade[i] = fade[i] - fade_step if fade[i] > fade_step else 0

        for x, d in enumerate(cols):
            if not d.active:
                if random.random() < spawn_p:
                    d.active = True
                    d.y = -random.uniform(0, 4)
                    d.speed = random.uniform(smin, smax)
                    d.length = random.randint(3, max_trail)
                continue

            # bright head
            if 0 <= d.y < WH:
                fade[int(d.y) * WW + x] = 255
            # trail
            for j in range(1, d.length):
                ty = int(d.y) - j
                if 0 <= ty < WH:
                    b = 255 - (j * 255 // d.length)
                    idx = ty * WW + x
                    if b > fade[idx]:
                        fade[idx] = b

            d.y += d.speed
            if d.y - d.length >= WH:
                d.active = False

        c = Canvas()
        for y in range(WH):
            for x in range(WW):
                v = fade[y * WW + x]
                if v:
                    c.set(x, y, v)
        c.push()
        tick.wait()
    clear_all()


ANIMS = {"radar": radar, "wave": wave, "marquee": marquee, "matrix": matrix}


# ---------------------------------------------------------------- plasma
def plasma(duration=20.0, fps=60):
    frames = max(1, math.ceil(duration * fps))
    t = 0.0
    tstep = 3.0 / fps
    # precompute per-pixel base terms
    sin = math.sin
    tick = Ticker(fps, duration)
    for _ in tick.frames(frames):
        c = Canvas()
        buf = c.buf
        for y in range(WH):
            for x in range(WW):
                v = (
                    sin(x / 4.0 + t)
                    + sin(y / 3.0 - t)
                    + sin((x + y) / 5.0 + t)
                    + sin(math.hypot(x - WW / 2, y - WH / 2) / 4.0 - t)
                )
                b = int((v + 4) / 8 * 255)
                buf[y * WW + x] = 0 if b < 0 else (255 if b > 255 else b)
        c.push()
        t += tstep
        tick.wait()
    clear_all()


# ---------------------------------------------------------------- fire
def fire(duration=20.0, fps=60):
    import random

    frames = max(1, math.ceil(duration * fps))
    heat = [0.0] * (WW * WH)
    tick = Ticker(fps, duration)
    for _ in tick.frames(frames):
        # seed bottom row with random embers
        base = (WH - 1) * WW
        for x in range(WW):
            heat[base + x] = random.uniform(160, 255)
        # propagate upward with cooling and horizontal drift
        for y in range(WH - 1):
            for x in range(WW):
                below = (y + 1) * WW + x
                left = heat[below - 1] if x > 0 else heat[below]
                right = heat[below + 1] if x < WW - 1 else heat[below]
                avg = (heat[below] * 2 + left + right) / 4.0
                heat[y * WW + x] = max(0.0, avg - random.uniform(8, 26))
        c = Canvas()
        buf = c.buf
        for i in range(WW * WH):
            v = int(heat[i])
            buf[i] = 255 if v > 255 else v
        c.push()
        tick.wait()
    clear_all()


# ---------------------------------------------------------------- game of life
def life(duration=25.0, fps=15):
    import random

    frames = max(1, math.ceil(duration * fps))
    grid = [1 if random.random() < 0.3 else 0 for _ in range(WW * WH)]
    prev_states = []
    fade = [0] * (WW * WH)
    tick = Ticker(fps, duration)
    for _ in tick.frames(frames):
        # render (with a soft fade for smoothness)
        c = Canvas()
        for i in range(WW * WH):
            if grid[i]:
                fade[i] = 255
            else:
                fade[i] = fade[i] - 40 if fade[i] > 40 else 0
            c.buf[i] = fade[i]
        c.push()

        # step Conway
        nxt = [0] * (WW * WH)
        for y in range(WH):
            for x in range(WW):
                n = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx = (x + dx) % WW
                        ny = (y + dy) % WH
                        n += grid[ny * WW + nx]
                i = y * WW + x
                nxt[i] = (
                    1 if (grid[i] and n in (2, 3)) or (not grid[i] and n == 3) else 0
                )

        # reseed if stagnant or extinct
        key = tuple(nxt)
        if sum(nxt) == 0 or key in prev_states:
            for _ in range(WW):
                nxt[random.randrange(WW * WH)] = 1
        prev_states.append(key)
        if len(prev_states) > 6:
            prev_states.pop(0)
        grid = nxt
        tick.wait()
    clear_all()


# ---------------------------------------------------------------- starfield warp
def starfield(duration=20.0, fps=60):
    import random

    frames = max(1, math.ceil(duration * fps))
    n = 60
    cx, cy = WW / 2.0, WH / 2.0

    def spawn():
        return [
            random.uniform(-cx, cx),
            random.uniform(-cy, cy),
            random.uniform(0.3, 1.0),
        ]

    stars = [spawn() for _ in range(n)]
    speed = 22.0 / fps
    tick = Ticker(fps, duration)
    for _ in tick.frames(frames):
        c = Canvas()
        for s in stars:
            s[2] -= speed * 0.03
            if s[2] <= 0.02:
                s[0], s[1], s[2] = random.uniform(-cx, cx), random.uniform(-cy, cy), 1.0
            px = cx + s[0] / s[2]
            py = cy + s[1] / s[2]
            b = int(min(255, (1.0 - s[2]) * 320))
            c.set(px, py, b)
        c.push()
        tick.wait()
    clear_all()


# ---------------------------------------------------------------- bounce (DVD)
def bounce(duration=20.0, fps=60):
    # a 3x3 blob bouncing across the whole wall, brightens on wall hits
    x, y = WW / 3.0, WH / 2.0
    vx, vy = 26.0 / fps, 17.0 / fps
    glow = 255
    frames = max(1, math.ceil(duration * fps))
    tick = Ticker(fps, duration)
    for _ in tick.frames(frames):
        x += vx
        y += vy
        hit = False
        if x <= 1 or x >= WW - 2:
            vx = -vx
            x = max(1, min(WW - 2, x))
            hit = True
        if y <= 1 or y >= WH - 2:
            vy = -vy
            y = max(1, min(WH - 2, y))
            hit = True
        if hit:
            glow = 255
        c = Canvas()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                c.set(x + dx, y + dy, glow)
        c.push()
        glow = max(120, glow - 6)
        tick.wait()
    clear_all()


# ---------------------------------------------------------------- ripple
def ripple(duration=20.0, fps=60):
    import random

    frames = max(1, math.ceil(duration * fps))
    drops = []  # each: [cx, cy, radius, life]
    tick = Ticker(fps, duration)
    grow = 18.0 / fps
    for f in tick.frames(frames):
        if random.random() < 4.0 / fps:  # ~4 new ripples/sec
            drops.append([random.uniform(0, WW), random.uniform(0, WH), 0.0, 1.0])
        c = Canvas()
        for d in drops:
            d[2] += grow
            d[3] -= 0.9 / fps
            r = d[2]
            b = int(max(0, d[3]) * 255)
            if b <= 0:
                continue
            steps = max(20, int(r * 5))
            for s in range(steps):
                a = 2 * math.pi * s / steps
                c.set(d[0] + math.cos(a) * r, d[1] + math.sin(a) * r, b)
        drops = [d for d in drops if d[3] > 0]
        c.push()
        tick.wait()
    clear_all()


ANIMS.update(
    {
        "plasma": plasma,
        "fire": fire,
        "life": life,
        "starfield": starfield,
        "bounce": bounce,
        "ripple": ripple,
    }
)


# ---------------------------------------------------------------- snake (self-playing)
def snake(duration=25.0, fps=30):
    import random

    frames = max(1, math.ceil(duration * fps))

    def new_food(body):
        while True:
            f = (random.randrange(WW), random.randrange(WH))
            if f not in body:
                return f

    # start in the middle moving right
    body = [(WW // 2 - i, WH // 2) for i in range(4)]
    direction = (1, 0)
    food = new_food(set(body))
    fade = [0] * (WW * WH)
    tick = Ticker(fps, duration)

    def try_dir(head, d, occupied):
        nx = (head[0] + d[0]) % WW
        ny = (head[1] + d[1]) % WH
        return (nx, ny) not in occupied, (nx, ny)

    for _ in tick.frames(frames):
        head = body[0]
        occ = set(body)

        # greedy AI: prefer moves that reduce distance to food, avoid self,
        # never reverse straight back.
        opts = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        opts = [d for d in opts if d != (-direction[0], -direction[1])]

        def score(d):
            ok, nxt = try_dir(head, d, occ - {body[-1]})
            if not ok:
                return (1, 999)  # blocked -> worst
            # toroidal distance to food
            dx = min((nxt[0] - food[0]) % WW, (food[0] - nxt[0]) % WW)
            dy = min((nxt[1] - food[1]) % WH, (food[1] - nxt[1]) % WH)
            return (0, dx + dy)

        opts.sort(key=score)
        chosen = None
        for d in opts:
            ok, nxt = try_dir(head, d, occ - {body[-1]})
            if ok:
                chosen = (d, nxt)
                break
        if chosen is None:
            # trapped: reset
            body = [(WW // 2 - i, WH // 2) for i in range(4)]
            direction = (1, 0)
            food = new_food(set(body))
            tick.wait()
            continue

        direction, nxt = chosen
        body.insert(0, nxt)
        if nxt == food:
            food = new_food(set(body))
            if len(body) > 40:
                body = body[:20]  # keep it lively, cap length
        else:
            body.pop()

        # render: fade trail, bright head, blinking food
        for i in range(len(fade)):
            fade[i] = fade[i] - 30 if fade[i] > 30 else 0
        c = Canvas()
        n = len(body)
        for idx, (bx, by) in enumerate(body):
            b = 255 - int(idx / max(1, n) * 150)
            fade[by * WW + bx] = b
        for i in range(len(fade)):
            if fade[i]:
                c.buf[i] = fade[i]
        # food pulses
        fb = 120 + int(135 * (0.5 + 0.5 * math.sin(time.perf_counter() * 6)))
        c.set(food[0], food[1], fb)
        c.push()
        tick.wait()
    clear_all()


ANIMS["snake"] = snake


# ---------------------------------------------------------------- pacman (self-playing)
def pacman(duration=30.0, fps=30, intro=True):
    """Grid/lane-based self-playing Pac-Man across the configured wall.

    Actors move one cell at a time in the 4 cardinal directions (authentic
    Pac-Man motion) with smooth interpolation between cells. Pac greedily
    heads for the nearest pellet; three ghosts each hunt differently
    (chaser / ambusher / scatter). A ghost catching Pac triggers the classic
    death spin, then the round restarts.
    """
    tick = Ticker(fps, duration)
    if intro:
        pac_intro(duration=min(4.0, duration), fps=fps)
        if tick.expired:
            return

    STEP = 2
    GC, GR = WW // STEP, WH // STEP
    DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    corners = [(1, 1), (GC - 2, 1), (1, GR - 2), (GC - 2, GR - 2)]

    def center(gx, gy):
        return gx * STEP + (STEP - 1) / 2.0, gy * STEP + (STEP - 1) / 2.0

    def in_bounds(gx, gy):
        return 0 <= gx < GC and 0 <= gy < GR

    def full_pellets():
        return set((x, y) for x in range(GC) for y in range(GR))

    def new_actor(gx, gy, d):
        return {"gx": gx, "gy": gy, "tx": gx, "ty": gy, "t": 1.0, "dir": d}

    def pos(a):
        x0, y0 = center(a["gx"], a["gy"])
        x1, y1 = center(a["tx"], a["ty"])
        return x0 + (x1 - x0) * a["t"], y0 + (y1 - y0) * a["t"]

    def step_toward(a, cps, target):
        """Advance along the current lane; at each cell pick the 4-dir move
        that best reduces Manhattan distance to target (no immediate reverse
        unless it is a dead end)."""
        a["t"] += cps
        while a["t"] >= 1.0:
            a["t"] -= 1.0
            a["gx"], a["gy"] = a["tx"], a["ty"]
            rev = (-a["dir"][0], -a["dir"][1])
            opts = []
            for d in DIRS:
                nx, ny = a["gx"] + d[0], a["gy"] + d[1]
                if not in_bounds(nx, ny):
                    continue
                dist = abs(target[0] - nx) + abs(target[1] - ny)
                opts.append((1 if d == rev else 0, dist, d, nx, ny))
            if not opts:
                a["t"] = 0.0
                return
            opts.sort(key=lambda o: (o[0], o[1]))
            _, _, d, nx, ny = opts[0]
            a["dir"] = d
            a["tx"], a["ty"] = nx, ny

    def spawn():
        p = new_actor(GC // 2, GR // 2, (1, 0))
        gs = [
            new_actor(1, 1, (1, 0)),
            new_actor(GC - 2, 1, (-1, 0)),
            new_actor(GC - 2, GR - 2, (-1, 0)),
        ]
        return p, gs

    pac, ghosts = spawn()
    pellets = full_pellets()
    pac_cps = 7.0 / fps
    ghost_cps = 5.2 / fps
    pac_r, gr = 2.6, 2.3

    def nearest_pellet(gx, gy):
        best, bd = None, 1e9
        for fx, fy in pellets:
            d = abs(fx - gx) + abs(fy - gy)
            if d < bd:
                bd, best = d, (fx, fy)
        return best

    mouth_t = 0.0
    frames = max(1, math.ceil(duration * fps))

    for f in tick.frames(frames):
        # --- Pac: greedy toward nearest pellet ---
        tgt = nearest_pellet(pac["gx"], pac["gy"]) or (pac["gx"], pac["gy"])
        step_toward(pac, pac_cps, tgt)
        pellets.discard((pac["gx"], pac["gy"]))
        pellets.discard((pac["tx"], pac["ty"]))
        if not pellets:
            pellets = full_pellets()

        # --- Ghosts: distinct targets ---
        # 0 = chaser (pac cell); 1 = ambusher (4 cells ahead of pac);
        # 2 = scatter (roams corners on a timer)
        ahead = (
            max(0, min(GC - 1, pac["tx"] + pac["dir"][0] * 4)),
            max(0, min(GR - 1, pac["ty"] + pac["dir"][1] * 4)),
        )
        scatter = corners[(f // (fps * 3)) % 4]
        gtargets = [(pac["tx"], pac["ty"]), ahead, scatter]
        for g, gt in zip(ghosts, gtargets):
            step_toward(g, ghost_cps, gt)

        px, py = pos(pac)
        caught = any(
            (pos(g)[0] - px) ** 2 + (pos(g)[1] - py) ** 2 < 2.5 for g in ghosts
        )
        if caught:
            for dc in _pac_death(
                px,
                py,
                fps,
                face=math.atan2(pac["dir"][1], pac["dir"][0]),
                r=pac_r + 0.6,
            ):
                if tick.expired:
                    break
                dc.push()
                tick.wait()
            pac, ghosts = spawn()
            pellets = full_pellets()
            continue

        # --- render ---
        c = Canvas()
        for fx, fy in pellets:
            cx, cy = center(fx, fy)
            c.set(cx, cy, 55)

        mouth_t += 0.5
        mouth = (0.06 + 0.40 * (0.5 + 0.5 * math.sin(mouth_t))) * math.pi
        face = math.atan2(pac["dir"][1], pac["dir"][0])
        _draw_pac(c, px, py, pac_r, face, mouth)

        for g in ghosts:
            gx, gy = pos(g)
            _draw_ghost(c, gx, gy, gr, 150, eye_dir=g["dir"][0])

        c.push()
        tick.wait()
    clear_all()


ANIMS["pacman"] = pacman


# ---------------------------------------------------------------- pac sprites
def _draw_pac(c, cx, cy, r, face, mouth, bright=255):
    rr = int(math.ceil(r))
    for dy in range(-rr, rr + 1):
        for dx in range(-rr, rr + 1):
            if dx * dx + dy * dy <= r * r:
                a = math.atan2(dy, dx)
                diff = abs((a - face + math.pi) % (2 * math.pi) - math.pi)
                if diff > mouth:  # outside mouth wedge -> body
                    c.set(cx + dx, cy + dy, bright)


def _draw_ghost(c, cx, cy, r, bright=170, eye_dir=1, t=0.0):
    rr = int(math.ceil(r))
    for dy in range(-rr, rr + 1):
        for dx in range(-rr, rr + 1):
            inside = False
            if dy <= 0:  # rounded dome
                if dx * dx + dy * dy <= r * r:
                    inside = True
            else:  # body + wavy skirt
                if abs(dx) <= r:
                    if dy == rr and (dx % 2 == 0):
                        inside = False  # skirt notch
                    else:
                        inside = True
            if inside:
                c.set(cx + dx, cy + dy, bright)
    # eyes read as brighter pixels over the dimmer body (monochrome contrast)
    ed = 1 if eye_dir > 0 else (-1 if eye_dir < 0 else 0)
    if r >= 4:
        for ex in (-2, 2):
            c.set(cx + ex + ed, cy - 1, 255)
    elif r >= 1.8:
        for ex in (-1, 1):
            c.set(cx + ex + (ed if ed else 0), cy - 1, 255)


def _draw_cherry(c, cx, cy, bright=255, t=0.0, scale=1.0):
    # two berries + stems + a leaf
    def put(dx, dy, brightness):
        c.set(cx + dx * scale, cy + dy * scale, brightness)

    r = 3
    for ox, oy in ((-3, 3), (3, 4)):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    put(ox + dx, oy + dy, bright)
        # little highlight
        put(ox - 1, oy - 1, 120)
    # stems meeting at top
    for i in range(6):
        put(-3 + i * 0.5, 3 - i, bright)
        put(3 - i * 0.3, 4 - i, bright)
    # leaf
    for dx in range(0, 4):
        put(1 + dx, -3 - (dx // 2), bright)


# ---------------------------------------------------------------- pac intro
def pac_intro(duration=6.0, fps=30):
    # Fit all three sprites even when the wall has only one or two panels.
    centers = [(i + 0.5) * WW / 3 for i in range(3)]
    radius = min(6.5, WW / 6 - 1)
    frames = max(1, math.ceil(duration * fps))
    tick = Ticker(fps, duration)
    for f in tick.frames(frames):
        t = f / fps
        c = Canvas()
        # Pac-Man (left) chomps, facing right
        mouth = (0.05 + 0.42 * (0.5 + 0.5 * math.sin(t * 8))) * math.pi
        _draw_pac(c, centers[0], 8, radius, 0.0, mouth)
        # Ghost (mid) bobs up and down
        gy = 8 + int(math.sin(t * 4) * 1.5)
        _draw_ghost(c, centers[1], gy, min(6, radius), 170, eye_dir=1, t=t)
        # Cherry (right) pulses
        cb = 150 + int(105 * (0.5 + 0.5 * math.sin(t * 5)))
        _draw_cherry(c, centers[2], 8, cb, scale=min(1.0, radius / 6.5))
        c.push()
        tick.wait()
    clear_all()


ANIMS["pac_intro"] = pac_intro


# ---------------------------------------------------------------- pac deadscreen
def _pac_death(cx, cy, fps, face=-math.pi / 2, r=6.5):
    """Classic death: mouth opens from the facing dir until Pac vanishes,
    then a small burst. Renders onto its own frames. Returns generator of
    Canvas frames so callers can overlay context if wanted."""
    frames = max(1, int(1.1 * fps))
    for i in range(frames):
        c = Canvas()
        mouth = (i / frames) * math.pi  # 0 -> pi (fully open = gone)
        _draw_pac(c, cx, cy, r, face, mouth)
        yield c
    # vanish burst
    burst = max(1, int(0.4 * fps))
    for i in range(burst):
        c = Canvas()
        rad = 1 + i * ((r - 0.5) / burst)
        b = int(255 * (1 - i / burst))
        for s in range(16):
            a = 2 * math.pi * s / 16
            c.set(cx + math.cos(a) * rad, cy + math.sin(a) * rad, b)
        yield c


def deadscreen(duration=8.0, fps=30):
    cx, cy = WW / 2.0, WH / 2.0
    tick = Ticker(fps, duration)
    pacx = min(cx + 6, WW - 7)

    # 1) Pac gets chased in, ghost approaches, then dies
    approach = int(2.0 * fps)
    for i in tick.frames(approach):
        c = Canvas()
        ghostx = 4 + i * ((pacx - 8) / approach)
        t = i / fps
        mouth = (0.05 + 0.4 * (0.5 + 0.5 * math.sin(t * 8))) * math.pi
        _draw_pac(c, pacx, cy, 6.5, math.pi, mouth)  # facing left toward ghost
        _draw_ghost(c, ghostx, cy, 5, 200, eye_dir=1, t=t)
        c.push()
        tick.wait()

    # 2) death animation
    for c in _pac_death(pacx, cy, fps, face=math.pi / 2):
        if tick.expired:
            break
        c.push()
        tick.wait()

    # 3) GAME OVER blink (scrolling since text is wide)
    msg = "GAME OVER"
    glyph_w = 4
    total = len(msg) * glyph_w
    hold = max(1, math.ceil(max(0.0, tick.deadline - time.perf_counter()) * fps))
    for f in tick.frames(hold):
        c = Canvas()
        # slow scroll once, then blink in place
        blink = (f // max(1, fps // 2)) % 2 == 0
        if blink:
            if total > WW:
                offset = int(f * 8 / fps) % (total + WW) - WW
            else:
                offset = total // 2 - WW // 2
            for i, ch in enumerate(msg):
                g = _FONT_BIG.get(ch, _FONT_BIG[" "])
                gx = i * glyph_w - offset
                for ry in range(5):
                    for rx in range(3):
                        if g[ry][rx] == "1":
                            c.set(gx + rx, 6 + ry, 255)
        c.push()
        tick.wait()
    clear_all()


ANIMS["deadscreen"] = deadscreen
ANIMS["loading"] = pac_intro


# ---------------------------------------------------------------- tetris
# Self-playing Tetris on an internal 16-wide x wall-width-tall board, displayed
# rotated 90 deg so pieces enter from the LEFT and stack toward the RIGHT.
# A "line" is therefore a full 16-tall vertical bar -> a line clear flashes
# right across all panels. An El-Tetris heuristic drives placement so
# the AI genuinely clears lines.
_TET_BASE = {
    "I": [(0, 0), (0, 1), (0, 2), (0, 3)],
    "O": [(0, 0), (0, 1), (1, 0), (1, 1)],
    "T": [(0, 0), (0, 1), (0, 2), (1, 1)],
    "S": [(0, 1), (0, 2), (1, 0), (1, 1)],
    "Z": [(0, 0), (0, 1), (1, 1), (1, 2)],
    "J": [(0, 0), (1, 0), (1, 1), (1, 2)],
    "L": [(0, 2), (1, 0), (1, 1), (1, 2)],
}
_TET_BRIGHT = {"I": 130, "O": 150, "T": 175, "S": 195, "Z": 115, "J": 210, "L": 120}


def _tet_rotations(cells):
    """All unique 90-degree rotations of a tetromino, each normalised so the
    minimum row and column are 0."""

    def norm(cs):
        mr = min(r for r, _ in cs)
        mc = min(c for _, c in cs)
        return tuple(sorted((r - mr, c - mc) for r, c in cs))

    outs, seen = [], set()
    cur = cells
    for _ in range(4):
        mr = max(r for r, _ in cur)
        cur = [(c, mr - r) for r, c in cur]  # rotate 90 CW
        n = norm(cur)
        if n not in seen:
            seen.add(n)
            outs.append([list(p) for p in n])
    return outs


_TET_SHAPES = {k: _tet_rotations(v) for k, v in _TET_BASE.items()}


def tetris(duration=30.0, fps=30):
    import random

    W, H = WH, WW
    grid = [[0] * W for _ in range(H)]
    tick = Ticker(fps, duration)

    def valid(cells, col, d):
        for cr, cc in cells:
            r, c = cr + d, cc + col
            if r < 0 or r >= H or c < 0 or c >= W or grid[r][c]:
                return False
        return True

    def features(g):
        heights = [0] * W
        holes = 0
        for c in range(W):
            seen = False
            for r in range(H):
                if g[r][c]:
                    if not seen:
                        heights[c] = H - r
                        seen = True
                elif seen:
                    holes += 1
        bump = sum(abs(heights[c] - heights[c + 1]) for c in range(W - 1))
        lines = sum(1 for r in range(H) if all(g[r]))
        agg = sum(heights)
        return -0.510066 * agg + 0.760666 * lines - 0.35663 * holes - 0.184483 * bump

    def best_placement(piece):
        best = None
        for cells in _TET_SHAPES[piece]:
            wdt = max(c for _, c in cells) + 1
            for col in range(0, W - wdt + 1):
                if not valid(cells, col, 0):
                    continue
                d = 0
                while valid(cells, col, d + 1):
                    d += 1
                for cr, cc in cells:
                    grid[cr + d][cc + col] = 1
                sc = features(grid)
                for cr, cc in cells:
                    grid[cr + d][cc + col] = 0
                if best is None or sc > best[0]:
                    best = (sc, cells, col, d)
        return best

    def draw(falling=None, flash=None, on=False):
        c = Canvas()
        for r in range(H):
            row = grid[r]
            for cc in range(W):
                v = row[cc]
                if v:
                    b = v
                    if flash and r in flash:
                        b = 255 if on else 35
                    c.set(r, cc, b)  # wall_x = r, wall_y = cc
        if falling:
            for r, cc, b in falling:
                c.set(r, cc, b)
        c.push()

    piece = random.choice(list(_TET_SHAPES))
    while not tick.expired:
        place = best_placement(piece)
        if tick.expired:
            break
        if place is None:  # topped out -> flash + reset
            for k in tick.frames(6):
                c = Canvas()
                b = 255 if k % 2 == 0 else 0
                for r in range(H):
                    for cc in range(W):
                        if grid[r][cc]:
                            c.set(r, cc, b)
                c.push()
                tick.wait()
            grid = [[0] * W for _ in range(H)]
            piece = random.choice(list(_TET_SHAPES))
            continue

        _, cells, col, land = place
        bright = _TET_BRIGHT[piece]
        for d in tick.frames(land + 1):  # animate the drop
            falling = [(cr + d, cc + col, 255) for cr, cc in cells]
            draw(falling=falling)
            tick.wait()
        if tick.expired:
            break
        for cr, cc in cells:  # lock it in
            grid[cr + d][cc + col] = bright

        full = [r for r in range(H) if all(grid[r])]
        if full:
            fset = set(full)
            for k in tick.frames(6):  # flash the completed bars
                draw(flash=fset, on=(k % 2 == 0))
                tick.wait()
            remaining = [grid[r] for r in range(H) if r not in fset]
            grid = [[0] * W for _ in range(len(full))] + remaining

        piece = random.choice(list(_TET_SHAPES))
    clear_all()


ANIMS["tetris"] = tetris


# ---------------------------------------------------------------- duo loop
def loop(duration=60.0, fps=30, block=60.0):
    """Alternate Pac-Man and Tetris in blocks, bounded by total duration."""
    deadline = time.perf_counter() + duration
    turns = [pacman, tetris]
    i = 0
    while time.perf_counter() < deadline:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        turns[i % 2](duration=min(block, remaining), fps=fps)
        i += 1
    clear_all()


ANIMS["loop"] = loop


def main(argv=None):
    global _wall
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("anim", nargs="?", default="radar", choices=list(ANIMS) + ["all"])
    add_panel_arguments(ap)
    ap.add_argument(
        "--duration",
        type=bounded_float(0.01, 86400),
        default=20.0,
        help="seconds per animation, or TOTAL for loop, including intro "
        "and transitions (default: 20; all uses this per entry)",
    )
    ap.add_argument(
        "--fps",
        type=bounded_int(1, 120),
        default=30,
        help="maximum frame rate (default: 30)",
    )
    ap.add_argument(
        "--block",
        type=bounded_float(0.01, 3600),
        default=60.0,
        help="maximum seconds per Pac-Man/Tetris block in loop (default: 60)",
    )
    ap.add_argument(
        "--text",
        default="HI OBE!",
        help="marquee text, 1-256 characters; unsupported glyphs are blank",
    )
    args = ap.parse_args(argv)
    validate_panels(ap, args.panels)
    if not 1 <= len(args.text) <= 256:
        ap.error("--text must contain 1-256 characters")
    names = (
        [name for name in ANIMS if name != "loop"]
        if args.anim == "all"
        else [args.anim]
    )
    try:
        with DDPWall(args.panels, args.port) as wall:
            configure(wall)
            for name in names:
                print(f"-> {name}")
                kw = {"duration": args.duration, "fps": args.fps}
                if name == "loop":
                    kw["block"] = args.block
                elif name == "marquee":
                    kw["text"] = args.text
                ANIMS[name](**kw)
    except KeyboardInterrupt:
        print("Interrupted; attempted to clear every panel.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"Animation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        _wall = None
    print("Animation finished; clear sent. UDP delivery is not acknowledged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
