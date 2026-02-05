"""
Quick test script to verify design rules export and retrieval
Run this after exporting from Altium to check if rules are accessible
"""
import json
from pathlib import Path
import requests

def test_export_files():
    """Check if export files exist"""
    print("=" * 60)
    print("1. Checking for Altium export files...")
    print("=" * 60)
    
    base_path = Path(".")
    
    # Check for export files
    export_files = sorted(
        base_path.glob("altium_export_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    if not export_files:
        print("❌ No export files found!")
        print("\nPlease run in Altium Designer:")
        print("  1. File → Run Script → command_server.pas")
        print("  2. Run 'StartServer' procedure")
        print("  3. Wait for success message")
        return False
    
    print(f"✅ Found {len(export_files)} export file(s)")
    print(f"\nMost recent: {export_files[0].name}")
    print(f"Modified: {export_files[0].stat().st_mtime}")
    
    return export_files[0]

def test_export_content(export_file):
    """Check export file content"""
    print("\n" + "=" * 60)
    print("2. Checking export file content...")
    print("=" * 60)
    
    try:
        with open(export_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ File is valid JSON")
        print(f"\nFile name: {data.get('file_name', 'Unknown')}")
        print(f"Export source: {data.get('export_source', 'Unknown')}")
        
        # Check for rules
        rules = data.get('rules', [])
        if not rules:
            print("\n❌ No rules found in export file!")
            print("\nPossible reasons:")
            print("  1. PCB has no design rules defined")
            print("  2. Export script failed to read rules")
            print("\nTo fix:")
            print("  1. In Altium: Design → Rules")
            print("  2. Add at least one rule (e.g., Clearance)")
            print("  3. Re-run export script")
            return False
        
        print(f"\n✅ Found {len(rules)} design rule(s)")
        
        # Show rule summary
        rule_types = {}
        for rule in rules:
            rule_type = rule.get('type', 'unknown')
            rule_types[rule_type] = rule_types.get(rule_type, 0) + 1
        
        print("\nRule types:")
        for rule_type, count in rule_types.items():
            print(f"  • {rule_type}: {count}")
        
        # Show first 3 rules
        print("\nFirst 3 rules:")
        for i, rule in enumerate(rules[:3]):
            name = rule.get('name', 'Unnamed')
            rule_type = rule.get('type', 'unknown')
            enabled = "✅" if rule.get('enabled', True) else "❌"
            print(f"  {i+1}. {enabled} {name} ({rule_type})")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False

def test_mcp_server():
    """Test MCP server endpoint"""
    print("\n" + "=" * 60)
    print("3. Testing MCP server endpoint...")
    print("=" * 60)
    
    try:
        response = requests.get("http://localhost:8765/drc/rules", timeout=5)
        
        if response.status_code != 200:
            print(f"❌ Server returned status {response.status_code}")
            return False
        
        data = response.json()
        
        if not data.get("success"):
            error = data.get("error", "Unknown error")
            message = data.get("message", "")
            print(f"❌ Server error: {error}")
            if message:
                print(f"\nMessage: {message}")
            return False
        
        rules = data.get("rules", [])
        stats = data.get("statistics", {})
        
        print(f"✅ MCP server is working!")
        print(f"\nTotal rules: {stats.get('total', 0)}")
        print(f"Enabled: {stats.get('enabled', 0)}")
        
        # Show rules by category
        rules_by_category = data.get("rules_by_category", {})
        if rules_by_category:
            print("\nRules by category:")
            for category, cat_rules in rules_by_category.items():
                print(f"  • {category}: {len(cat_rules)}")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to MCP server!")
        print("\nPlease start the MCP server:")
        print("  python mcp_server.py")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Design Rules Export Test")
    print("=" * 60)
    
    # Test 1: Check export files
    export_file = test_export_files()
    if not export_file:
        print("\n❌ Test failed: No export files")
        return
    
    # Test 2: Check export content
    if not test_export_content(export_file):
        print("\n❌ Test failed: Export file has no rules")
        return
    
    # Test 3: Test MCP server
    if not test_mcp_server():
        print("\n❌ Test failed: MCP server not working")
        return
    
    # All tests passed!
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nYou can now use 'View Design Rules' in the UI")
    print("The button should display all rules from Altium")

if __name__ == "__main__":
    main()
