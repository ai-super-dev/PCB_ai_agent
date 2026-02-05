#!/usr/bin/env python3
"""Check what keys are available for different rule types"""
import olefile
import re

pcb_path = "PCB_Project/Y904A23-GF-DYPCB-V1.0.PcbDoc"
ole = olefile.OleFileIO(pcb_path)

if ole.exists('Rules6/Data'):
    data = ole.openstream('Rules6/Data').read()
    text = data.decode('latin-1', errors='ignore')
    
    # Find Width rule
    print("="*60)
    print("WIDTH RULE:")
    width_match = re.search(r'\|NAME=Width\|[^|]*\|RULEKIND=Width[^|]*(?:\|[^|]*)*', text)
    if width_match:
        rule_text = width_match.group(0)[:2000]
        print(rule_text)
        keys = re.findall(r'\|([A-Z0-9_]+)=', rule_text)
        print(f"\nKeys: {set(keys)}")
    
    # Find RoutingCorners rule
    print("\n" + "="*60)
    print("ROUTING CORNERS RULE:")
    corner_match = re.search(r'\|NAME=RoutingCorners\|[^|]*\|RULEKIND=RoutingCorners[^|]*(?:\|[^|]*)*', text)
    if corner_match:
        rule_text = corner_match.group(0)[:2000]
        print(rule_text)
        keys = re.findall(r'\|([A-Z0-9_]+)=', rule_text)
        print(f"\nKeys: {set(keys)}")
    
    # Find RoutingVias rule
    print("\n" + "="*60)
    print("ROUTING VIAS RULE:")
    via_match = re.search(r'\|NAME=RoutingVias\|[^|]*\|RULEKIND=RoutingViaStyle[^|]*(?:\|[^|]*)*', text)
    if via_match:
        rule_text = via_match.group(0)[:2000]
        print(rule_text)
        keys = re.findall(r'\|([A-Z0-9_]+)=', rule_text)
        print(f"\nKeys: {set(keys)}")
    
    # Find RoutingTopology rule
    print("\n" + "="*60)
    print("ROUTING TOPOLOGY RULE:")
    topo_match = re.search(r'\|NAME=RoutingTopology\|[^|]*\|RULEKIND=RoutingTopology[^|]*(?:\|[^|]*)*', text)
    if topo_match:
        rule_text = topo_match.group(0)[:2000]
        print(rule_text)
        keys = re.findall(r'\|([A-Z0-9_]+)=', rule_text)
        print(f"\nKeys: {set(keys)}")

ole.close()
