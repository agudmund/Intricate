#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - data/BloomNodeData.py BloomNodeData data class
-State for a particle scatter controller node, pure Python for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from dataclasses import dataclass, field
from data.NodeData import NodeData


@dataclass
class BloomNodeData(NodeData):
    node_type:       str   = field(default="bloom")
    title:           str   = field(default="Bloom")
    width:           float = field(default=260.0)
    height:          float = field(default=330.0)
    scatter_mode:    str   = field(default="sprinkle")   # "sprinkle" or "orbital"
    particle_count:  int   = field(default=8000)
    seed:            int   = field(default=42)
    density_falloff: str   = field(default="uniform")    # "uniform", "center", "edge"
    stiffness:       float = field(default=0.10)         # orbital lerp_rate 0.01–1.0
    speed:           float = field(default=0.70)         # orbital flow speed 0.01–3.0
    distance:        float = field(default=576.0)        # scatter radius in scene pixels
    depth_front:     bool  = field(default=False)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["scatter_mode"]    = self.scatter_mode
        data["particle_count"]  = self.particle_count
        data["seed"]            = self.seed
        data["density_falloff"] = self.density_falloff
        data["stiffness"]       = self.stiffness
        data["speed"]           = self.speed
        data["distance"]        = self.distance
        data["depth_front"]     = self.depth_front
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'BloomNodeData':
        import uuid as _uuid
        return cls(
            node_id         = data.get("node_id",         0),
            title           = data.get("title",           "Bloom"),
            uuid            = data.get("uuid",            _uuid.uuid4().hex),
            x               = float(data.get("x",         0.0)),
            y               = float(data.get("y",         0.0)),
            width           = float(data.get("width",     260.0)),
            height          = float(data.get("height",    330.0)),
            ports_visible   = data.get("ports_visible",   False),
            scatter_mode    = data.get("scatter_mode",    "sprinkle"),
            particle_count  = data.get("particle_count",  8000),
            seed            = data.get("seed",            42),
            density_falloff = data.get("density_falloff", "uniform"),
            stiffness       = float(data.get("stiffness", 0.10)),
            speed           = float(data.get("speed",     0.70)),
            distance        = float(data.get("distance",  576.0)),
            depth_front     = data.get("depth_front",     False),
        )
