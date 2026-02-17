"""Test HTML DRC report parsing"""
import re
from pathlib import Path

# Read the HTML report
drc_report_path = Path("PCB_Project/Project Outputs for PCB_Project/Design Rule Check - Y904A23-GF-DYPCB-V1.html")

if drc_report_path.exists():
    print(f"✅ Found DRC report: {drc_report_path}")
    
    with open(drc_report_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    print(f"📄 HTML file size: {len(html_content)} bytes")
    
    # Test clearance pattern
    clearance_pattern = r'Clearance Constraint:.*?Between (.*?) And (.*?)</acronym>'
    clearance_matches = re.findall(clearance_pattern, html_content, re.DOTALL)
    print(f"\n🔍 Clearance violations found: {len(clearance_matches)}")
    for i, match in enumerate(clearance_matches, 1):
        print(f"  {i}. Between: {match[0][:50]}... And: {match[1][:50]}...")
    
    # Test short-circuit pattern
    short_pattern = r'Short-Circuit Constraint:.*?Between (.*?) And (.*?)</acronym>'
    short_matches = re.findall(short_pattern, html_content, re.DOTALL)
    print(f"\n⚡ Short-circuit violations found: {len(short_matches)}")
    for i, match in enumerate(short_matches, 1):
        print(f"  {i}. Between: {match[0][:50]}... And: {match[1][:50]}...")
    
    # Test un-routed pattern
    unrouted_pattern = r'Un-Routed Net Constraint:.*?Net (.*?) Between (.*?) And (.*?)</acronym>'
    unrouted_matches = re.findall(unrouted_pattern, html_content, re.DOTALL)
    print(f"\n🔌 Un-routed net violations found: {len(unrouted_matches)}")
    for i, match in enumerate(unrouted_matches, 1):
        print(f"  {i}. Net: {match[0][:30]}... Between: {match[1][:30]}... And: {match[2][:30]}...")
    
    print(f"\n📊 Total violations: {len(clearance_matches) + len(short_matches) + len(unrouted_matches)}")
    
else:
    print(f"❌ DRC report not found at: {drc_report_path}")
