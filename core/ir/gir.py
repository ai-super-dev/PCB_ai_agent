"""
Geometry Internal Representation (G-IR)
Per Architecture Spec §4.1

Models geometric and topological aspects of PCB designs.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class LayerKind(str, Enum):
    """Layer type"""
    SIGNAL = "signal"
    PLANE = "plane"
    POWER = "power"
    GROUND = "ground"
    SOLDER_MASK = "solder_mask"
    SILKSCREEN = "silkscreen"
    PASTE = "paste"


class Layer(BaseModel):
    """PCB Layer definition"""
    id: str = Field(..., description="Unique layer identifier")
    name: str = Field(..., description="Layer name (e.g., 'Top', 'GND')")
    kind: LayerKind = Field(..., description="Layer type")
    index: int = Field(..., description="Layer stack index")


class StackupLayer(BaseModel):
    """Stackup layer definition"""
    layer_id: str = Field(..., description="Reference to layer ID")
    thickness_mm: Optional[float] = Field(None, description="Layer thickness in mm")


class Dielectric(BaseModel):
    """Dielectric material between layers"""
    material: str = Field(..., description="Material name")
    thickness_mm: float = Field(..., description="Thickness in mm")
    dielectric_constant: Optional[float] = Field(None, description="Er value")


class Stackup(BaseModel):
    """PCB layer stackup"""
    layers: List[str] = Field(..., description="Ordered list of layer IDs")
    thickness_mm: float = Field(..., description="Total board thickness in mm")
    dielectrics: List[Dielectric] = Field(default_factory=list, description="Dielectric layers")


class BoardOutline(BaseModel):
    """Board outline definition"""
    polygon: List[List[float]] = Field(..., description="List of [x, y] coordinates forming outline")


class Board(BaseModel):
    """PCB Board geometry"""
    outline: BoardOutline = Field(..., description="Board outline")
    layers: List[Layer] = Field(..., description="List of layers")
    stackup: Stackup = Field(..., description="Layer stackup definition")


class Net(BaseModel):
    """Net definition"""
    id: str = Field(..., description="Unique net identifier")
    name: str = Field(..., description="Net name (e.g., 'GND', 'VCC')")


class TrackSegment(BaseModel):
    """Track segment definition"""
    from_pos: List[float] = Field(..., description="Start position [x, y] in mm")
    to_pos: List[float] = Field(..., description="End position [x, y] in mm")
    width_mm: float = Field(..., description="Track width in mm")


class Track(BaseModel):
    """Track (trace) definition"""
    id: str = Field(..., description="Unique track identifier")
    net_id: str = Field(..., description="Net this track belongs to")
    layer_id: str = Field(..., description="Layer this track is on")
    segments: List[TrackSegment] = Field(..., description="Track segments")


class Via(BaseModel):
    """Via definition"""
    id: str = Field(..., description="Unique via identifier")
    net_id: str = Field(..., description="Net this via belongs to")
    position: List[float] = Field(..., description="Via position [x, y] in mm")
    drill_mm: float = Field(..., description="Drill diameter in mm")
    layers: List[str] = Field(..., description="Layer IDs this via connects")


class Pad(BaseModel):
    """Pad definition within a footprint"""
    id: str = Field(..., description="Unique pad identifier")
    net_id: Optional[str] = Field(None, description="Net this pad is connected to")
    shape: str = Field(..., description="Pad shape: 'rect', 'round', 'oval'")
    size_mm: List[float] = Field(..., description="Pad size [width, height] in mm")
    position: List[float] = Field(..., description="Pad position relative to footprint center [x, y] in mm")
    layer: str = Field(..., description="Layer this pad is on")


class Footprint(BaseModel):
    """Footprint (component placement) definition"""
    id: str = Field(..., description="Unique footprint identifier")
    ref: str = Field(..., description="Reference designator (e.g., 'U1', 'R1')")
    position: List[float] = Field(..., description="Position [x, y] in mm")
    rotation_deg: float = Field(default=0.0, description="Rotation in degrees")
    layer: str = Field(..., description="Layer this footprint is on")
    pads: List[Pad] = Field(default_factory=list, description="Pads in this footprint")
    footprint_name: Optional[str] = Field(None, description="Footprint library name")


class GeometryIR(BaseModel):
    """
    Complete Geometry Internal Representation
    Per Architecture Spec §4.1
    """
    board: Board = Field(..., description="Board definition")
    nets: List[Net] = Field(default_factory=list, description="List of nets")
    tracks: List[Track] = Field(default_factory=list, description="List of tracks")
    vias: List[Via] = Field(default_factory=list, description="List of vias")
    footprints: List[Footprint] = Field(default_factory=list, description="List of footprints")

    class Config:
        json_schema_extra = {
            "example": {
                "board": {
                    "outline": {"polygon": [[0, 0], [100, 0], [100, 80], [0, 80]]},
                    "layers": [
                        {"id": "L1", "name": "Top", "kind": "signal", "index": 1},
                        {"id": "L2", "name": "GND", "kind": "plane", "index": 2}
                    ],
                    "stackup": {
                        "layers": ["L1", "L2"],
                        "thickness_mm": 1.6,
                        "dielectrics": []
                    }
                },
                "nets": [
                    {"id": "net-gnd", "name": "GND"},
                    {"id": "net-vcc", "name": "VCC"}
                ],
                "tracks": [
                    {
                        "id": "trk1",
                        "net_id": "net-gnd",
                        "layer_id": "L1",
                        "segments": [
                            {"from_pos": [10, 10], "to_pos": [30, 10], "width_mm": 0.2}
                        ]
                    }
                ],
                "vias": [
                    {
                        "id": "via1",
                        "net_id": "net-gnd",
                        "position": [30, 10],
                        "drill_mm": 0.3,
                        "layers": ["L1", "L2"]
                    }
                ],
                "footprints": [
                    {
                        "id": "fp-u1",
                        "ref": "U1",
                        "position": [20, 20],
                        "rotation_deg": 90,
                        "layer": "L1",
                        "pads": [
                            {
                                "id": "pad1",
                                "net_id": "net-gnd",
                                "shape": "rect",
                                "size_mm": [1, 1],
                                "position": [0, 0],
                                "layer": "L1"
                            }
                        ]
                    }
                ]
            }
        }
