"""Quick Test - Week 1 Features"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing Week 1 Features...")
print()

from tools.altium_file_reader import AltiumFileReader
from adapters.altium.importer import AltiumImporter
from core.artifacts.store import ArtifactStore
from runtime.routing.routing_module import RoutingModule
from runtime.drc.drc_module import DRCModule
from core.ir.cir import ConstraintIR, Rule, RuleType, RuleScope, RuleParams
from core.artifacts.models import Artifact, ArtifactType, ArtifactMeta, SourceEngine, CreatedBy

# Test 1: Python File Reader
reader = AltiumFileReader()
data = reader.read_pcb('PCB_Project/Y904A23-GF-DYPCB-V1.0.PcbDoc')
tracks = data["statistics"]["track_count"]
vias = data["statistics"]["via_count"]
print(f'[1] Python File Reader: PASS (Tracks: {tracks}, Vias: {vias})')

# Test 2: G-IR Creation
importer = AltiumImporter()
gir = importer.import_pcb_direct('PCB_Project/Y904A23-GF-DYPCB-V1.0.PcbDoc')
print(f'[2] G-IR Creation: PASS (Layers: {len(gir.board.layers)})')

# Test 3: Artifact Store
store = ArtifactStore()
board = store.create(importer.create_pcb_board_artifact(gir, 'test.PcbDoc'))
print(f'[3] Artifact Store: PASS (ID: {board.id[:8]}...)')

# Test 4: Routing Module
routing = RoutingModule(store)
routing.route_net(board.id, 'net-1', [0,0], [100,100], 'L1', 0.25)
print('[4] Routing Module: PASS')

# Test 5: C-IR Creation
cir = ConstraintIR(
    rules=[
        Rule(id='r1', type=RuleType.CLEARANCE, scope=RuleScope(), 
             params=RuleParams(min_clearance_mm=0.2), enabled=True)
    ], 
    netclasses=[]
)
constraint = store.create(Artifact(
    type=ArtifactType.CONSTRAINT_RULESET, 
    data=cir.model_dump(), 
    meta=ArtifactMeta(source_engine=SourceEngine.ALTIUM, created_by=CreatedBy.ENGINE)
))
print('[5] C-IR Creation: PASS')

# Test 6: DRC Module
drc = DRCModule(store)
drc.run_drc(board.id, constraint.id)
print('[6] DRC Module: PASS')

print()
print('=' * 40)
print('ALL WEEK 1 TESTS PASSED!')
print('=' * 40)
