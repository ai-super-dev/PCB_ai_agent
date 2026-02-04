"""
Internal Representation (IR) module
Contains G-IR (Geometry IR) and C-IR (Constraint IR) schemas
"""

from .gir import Board, Net, Track, Via, Footprint, GeometryIR
from .cir import Rule, Netclass, ConstraintIR

__all__ = [
    'Board', 'Net', 'Track', 'Via', 'Footprint', 'GeometryIR',
    'Rule', 'Netclass', 'ConstraintIR'
]
