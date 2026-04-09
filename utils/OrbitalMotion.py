#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/OrbitalMotion.py orbital torus knot engine
-Pure-math multi-ring particle swarm with wave modulation and 3D rotation for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math


class OrbitalSwarm:
    """
    Pure-math engine for an orbital torus knot particle swarm.

    Computes (x, y, depth, hue, saturation, lightness) per particle per tick.
    No Qt, no rendering — just the motion curve. Caller decides how to paint.

    The swarm arranges particles into concentric rings. Each ring flows in
    alternating directions. Wave offsets modulate ring radius. Three Euler
    rotations (pitch, yaw, roll) per ring create the torus knot structure.
    A spherical morph parameter blends between a flat wave field and
    interlocking orbital shells.

    Positions lerp toward computed targets each tick for organic smoothing.

    Tuning:
        rings       — number of concentric rings
        radius      — base distance from center
        spread      — wave amplitude (ring breathing)
        twist       — wave frequency and z-oscillation
        speed       — flow rate
        morph       — 0.0 = flat wave field, 1.0 = full spherical torus
        lerp_rate   — smoothing factor per tick (0..1, lower = smoother)
    """

    __slots__ = (
        'count', 'rings', 'radius', 'spread', 'twist', 'speed', 'morph',
        'lerp_rate', '_time', '_px', '_py', '_pz',
    )

    def __init__(
        self,
        count:     int   = 2000,
        rings:     float = 21.79,
        radius:    float = 10.0,
        spread:    float = 69.0,
        twist:     float = 0.6,
        speed:     float = 0.7,
        morph:     float = 1.0,
        lerp_rate: float = 0.1,
    ):
        self.count     = count
        self.rings     = rings
        self.radius    = radius
        self.spread    = spread
        self.twist     = twist
        self.speed     = speed
        self.morph     = morph
        self.lerp_rate = lerp_rate
        self._time     = 0.0

        # Current smoothed positions (start scattered)
        self._px = [(hash(i) % 200 - 100) * 0.5 for i in range(count)]
        self._py = [(hash(i * 7 + 3) % 200 - 100) * 0.5 for i in range(count)]
        self._pz = [0.0] * count

    def tick(self, dt: float) -> None:
        """
        Advance the simulation by dt seconds.

        After calling tick(), read positions and colors via particle() or
        iterate with particles().
        """
        self._time += dt * self.speed

        t       = self._time
        n       = self.count
        lr      = self.lerp_rate
        _cos    = math.cos
        _sin    = math.sin
        _floor  = math.floor
        _pi2    = math.pi * 2.0

        safeRings       = max(1.0, _floor(self.rings))
        particlesPerRing = max(1.0, n / safeRings)
        baseRadius       = self.radius
        ringSpread       = self.spread
        twist            = self.twist
        morph            = self.morph

        px = self._px
        py = self._py
        pz = self._pz

        for i in range(n):
            rId  = int(i / particlesPerRing)
            pId  = i % int(particlesPerRing)

            pNorm = pId / particlesPerRing
            rNorm = rId / safeRings

            angle     = pNorm * _pi2
            flowAngle = angle + (t * (1.0 if rId % 2 == 0 else -1.0))

            ringPhase = rNorm * _pi2

            # Wave-modulated radius
            waveOffset    = _sin(flowAngle * twist + ringPhase * 5.0 + t) * ringSpread
            currentRadius = baseRadius + waveOffset * (1.0 - morph * 0.5)

            # Base position
            x = _cos(flowAngle) * currentRadius
            y = _sin(flowAngle) * currentRadius
            z = _sin(flowAngle * max(1.0, twist) + ringPhase) * 15.0 * (1.0 - morph)

            # Euler rotation per ring — creates the torus knot structure
            pitch = ringPhase * 2.0 * morph + t * 0.2
            yaw   = ringPhase * math.pi * morph - t * 0.1
            roll  = ringPhase * 0.5 + t * 0.15

            cP, sP = _cos(pitch), _sin(pitch)
            cY, sY = _cos(yaw),   _sin(yaw)
            cR, sR = _cos(roll),  _sin(roll)

            # Pitch (rotate y,z)
            y1 = y * cP - z * sP
            z1 = y * sP + z * cP

            # Yaw (rotate x,z)
            x2 = x * cY + z1 * sY
            z2 = -x * sY + z1 * cY

            # Roll (rotate x,y)
            x3 = x2 * cR - y1 * sR
            y3 = x2 * sR + y1 * cR

            # Lerp toward target
            px[i] += (x3 - px[i]) * lr
            py[i] += (y3 - py[i]) * lr
            pz[i] += (z2 - pz[i]) * lr

    def particle(self, i: int) -> tuple[float, float, float, float, float, float]:
        """
        Return (x, y, depth, hue, saturation, lightness) for particle i.

        depth is the z-coordinate — use it for opacity, scale, or parallax.
        HSL values are 0..1.
        """
        t = self._time

        safeRings        = max(1.0, math.floor(self.rings))
        particlesPerRing = max(1.0, self.count / safeRings)
        rId  = int(i / particlesPerRing)
        pId  = i % int(particlesPerRing)
        pNorm = pId / particlesPerRing
        rNorm = rId / safeRings

        angle     = pNorm * math.pi * 2.0
        flowAngle = angle + (t * (1.0 if rId % 2 == 0 else -1.0))

        # Color
        hueBase    = rNorm + (t * 0.05) + (math.sin(flowAngle) * 0.1)
        hue        = hueBase - math.floor(hueBase)
        saturation = 0.7 + 0.3 * math.cos(flowAngle * 3.0)
        lightness  = 0.4 + 0.4 * math.sin(flowAngle * 2.0 - t)
        lightness *= (self._pz[i] / max(1.0, self.radius) * 0.5 + 0.5)
        lightness  = min(1.0, max(0.05, lightness))

        return (self._px[i], self._py[i], self._pz[i], hue, saturation, lightness)

    def particles(self):
        """Yield (x, y, depth, hue, saturation, lightness) for every particle."""
        for i in range(self.count):
            yield self.particle(i)

    def positions_flat(self) -> tuple[list[float], list[float], list[float]]:
        """Return (xs, ys, zs) lists — efficient for bulk rendering."""
        return self._px, self._py, self._pz
