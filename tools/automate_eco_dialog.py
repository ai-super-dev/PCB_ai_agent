"""
Windows API-based ECO Dialog Automation
This script uses Windows API to find and click ECO dialog buttons automatically.
Called from Altium DelphiScript when ECO dialog appears.

Requires: pip install pywin32
"""
try:
    import win32gui
    import win32con
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    print("[ECO Automation] pywin32 not installed. Install with: pip install pywin32")
    WIN32_AVAILABLE = False

import time
import sys

def find_window_by_title(title_keywords):
    """Find window by title keywords"""
    def callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd):
            window_title = win32gui.GetWindowText(hwnd)
            for keyword in title_keywords:
                if keyword.lower() in window_title.lower():
                    windows.append((hwnd, window_title))
        return True
    
    windows = []
    win32gui.EnumWindows(callback, windows)
    return windows

def find_button_by_text(parent_hwnd, button_text_keywords):
    """Find button by text within a parent window"""
    def callback(hwnd, buttons):
        try:
            if win32gui.IsWindowVisible(hwnd):
                button_text = win32gui.GetWindowText(hwnd)
                if button_text:  # Only check non-empty text
                    for keyword in button_text_keywords:
                        if keyword.lower() in button_text.lower():
                            buttons.append((hwnd, button_text))
        except:
            pass
        return True
    
    buttons = []
    try:
        win32gui.EnumChildWindows(parent_hwnd, callback, buttons)
    except:
        pass
    return buttons

def find_all_buttons(parent_hwnd):
    """Find all buttons in a window (for debugging)"""
    def callback(hwnd, buttons):
        try:
            if win32gui.IsWindowVisible(hwnd):
                button_text = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)
                if 'button' in class_name.lower() or button_text:
                    buttons.append((hwnd, button_text, class_name))
        except:
            pass
        return True
    
    buttons = []
    try:
        win32gui.EnumChildWindows(parent_hwnd, callback, buttons)
    except:
        pass
    return buttons

def click_button(hwnd):
    """Click a button by sending BM_CLICK message"""
    try:
        # Send BM_CLICK message
        win32api.SendMessage(hwnd, win32con.BM_CLICK, 0, 0)
        return True
    except Exception as e:
        print(f"Error clicking button: {e}")
        return False

def automate_eco_dialog():
    """Main function to automate ECO dialog"""
    if not WIN32_AVAILABLE:
        print("[ECO Automation] Cannot automate: pywin32 not available")
        print("[ECO Automation] Install with: pip install pywin32")
        return False
    
    print("[ECO Automation] Starting ECO dialog automation...")
    print("[ECO Automation] Waiting for ECO dialog to appear...")
    
    # Wait for dialog to appear (up to 30 seconds - give Altium more time)
    eco_dialog = None
    dialog_title = ""
    for i in range(60):  # 30 seconds total
        time.sleep(0.5)
        windows = find_window_by_title([
            'Engineering Change Order',
            'Update PCB Document',
            'ECO',
            'Engineering Change',
            'Change Order',
            'Update',
            'PCB Document'
        ])
        if windows:
            # Find the most likely ECO dialog (usually the first one)
            for hwnd, title in windows:
                # Prioritize dialogs with "ECO" or "Change Order" in title
                if any(kw in title.lower() for kw in ['eco', 'change order', 'engineering']):
                    eco_dialog = hwnd
                    dialog_title = title
                    print(f"[ECO Automation] Found ECO dialog: {dialog_title}")
                    break
            if eco_dialog:
                break
            # If no prioritized dialog, use first one
            eco_dialog = windows[0][0]
            dialog_title = win32gui.GetWindowText(eco_dialog)
            print(f"[ECO Automation] Found potential ECO dialog: {dialog_title}")
            break
        if i % 10 == 0 and i > 0:
            print(f"[ECO Automation] Still waiting for dialog... ({i*0.5:.1f}s)")
    
    if not eco_dialog:
        print("[ECO Automation] ECO dialog not found after 30 seconds")
        print("[ECO Automation] Trying to find any Altium dialog...")
        # Last resort: find any visible window that might be the ECO dialog
        def find_any_dialog(hwnd, dialogs):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)
                if 'dialog' in class_name.lower() and title:
                    dialogs.append((hwnd, title))
            return True
        
        all_dialogs = []
        win32gui.EnumWindows(find_any_dialog, all_dialogs)
        if all_dialogs:
            print(f"[ECO Automation] Found {len(all_dialogs)} dialogs, checking first few...")
            for hwnd, title in all_dialogs[:5]:
                print(f"  - {title}")
                # Check if it has buttons we're looking for
                buttons = find_all_buttons(hwnd)
                has_validate = any('valid' in btn[1].lower() for btn in buttons if btn[1])
                has_execute = any('execut' in btn[1].lower() for btn in buttons if btn[1])
                if has_validate and has_execute:
                    eco_dialog = hwnd
                    dialog_title = title
                    print(f"[ECO Automation] Found ECO dialog by button detection: {dialog_title}")
                    break
        if not eco_dialog:
            print("[ECO Automation] ECO dialog not found. Dialog may have already closed or not appeared.")
            return False
    
    # Bring dialog to front
    try:
        win32gui.SetForegroundWindow(eco_dialog)
        win32gui.BringWindowToTop(eco_dialog)
        time.sleep(0.5)
    except:
        pass
    
    # Debug: List all buttons for troubleshooting
    all_buttons = find_all_buttons(eco_dialog)
    if all_buttons:
        print(f"[ECO Automation] Found {len(all_buttons)} buttons in dialog:")
        for btn in all_buttons[:10]:  # Show first 10
            print(f"  - '{btn[1]}' (class: {btn[2]})")
    
    # Step 1: Find and click "Validate Changes" button
    print("[ECO Automation] Looking for 'Validate Changes' button...")
    validate_clicked = False
    validate_buttons = find_button_by_text(eco_dialog, ['Validate', 'validate'])
    if validate_buttons:
        print(f"[ECO Automation] Found Validate button: '{validate_buttons[0][1]}'")
        # Try clicking multiple times if needed
        for attempt in range(5):  # More attempts
            try:
                # Bring window to front before clicking
                win32gui.SetForegroundWindow(eco_dialog)
                win32gui.BringWindowToTop(eco_dialog)
                time.sleep(0.2)
                
                if click_button(validate_buttons[0][0]):
                    print("[ECO Automation] Clicked Validate Changes")
                    time.sleep(3)  # Wait longer for validation to complete
                    validate_clicked = True
                    break
                else:
                    print(f"[ECO Automation] Click attempt {attempt+1} failed, retrying...")
                    time.sleep(0.5)
            except Exception as e:
                print(f"[ECO Automation] Exception during Validate click: {e}")
                time.sleep(0.5)
    else:
        print("[ECO Automation] Validate button not found by text")
        # Try to find by common button patterns
        print("[ECO Automation] Searching all buttons for Validate...")
        for btn in all_buttons:
            if btn[1] and 'valid' in btn[1].lower():
                print(f"[ECO Automation] Found potential Validate button: '{btn[1]}'")
                try:
                    win32gui.SetForegroundWindow(eco_dialog)
                    time.sleep(0.2)
                    if click_button(btn[0]):
                        print("[ECO Automation] Clicked Validate")
                        time.sleep(3)
                        validate_clicked = True
                        break
                except Exception as e:
                    print(f"[ECO Automation] Exception: {e}")
                    continue
    
    if not validate_clicked:
        print("[ECO Automation] WARNING: Could not click Validate button")
        print("[ECO Automation] Continuing anyway - Execute might work...")
    
    # Step 2: Find and click "Execute Changes" button
    print("[ECO Automation] Looking for 'Execute Changes' button...")
    execute_clicked = False
    execute_buttons = find_button_by_text(eco_dialog, ['Execute', 'execute'])
    if execute_buttons:
        print(f"[ECO Automation] Found Execute button: '{execute_buttons[0][1]}'")
        for attempt in range(5):  # More attempts
            try:
                win32gui.SetForegroundWindow(eco_dialog)
                win32gui.BringWindowToTop(eco_dialog)
                time.sleep(0.2)
                
                if click_button(execute_buttons[0][0]):
                    print("[ECO Automation] Clicked Execute Changes")
                    time.sleep(5)  # Wait longer for execution to complete
                    execute_clicked = True
                    break
                else:
                    print(f"[ECO Automation] Click attempt {attempt+1} failed, retrying...")
                    time.sleep(0.5)
            except Exception as e:
                print(f"[ECO Automation] Exception during Execute click: {e}")
                time.sleep(0.5)
    else:
        print("[ECO Automation] Execute button not found by text")
        for btn in all_buttons:
            if btn[1] and 'execut' in btn[1].lower():
                print(f"[ECO Automation] Found potential Execute button: '{btn[1]}'")
                try:
                    win32gui.SetForegroundWindow(eco_dialog)
                    time.sleep(0.2)
                    if click_button(btn[0]):
                        print("[ECO Automation] Clicked Execute")
                        time.sleep(5)
                        execute_clicked = True
                        break
                except Exception as e:
                    print(f"[ECO Automation] Exception: {e}")
                    continue
    
    if not execute_clicked:
        print("[ECO Automation] ERROR: Could not click Execute button")
        print("[ECO Automation] ECO transfer may not have completed")
        return False
    
    # Step 3: Find and click "Close" or "OK" button
    print("[ECO Automation] Looking for 'Close' button...")
    close_clicked = False
    close_buttons = find_button_by_text(eco_dialog, ['Close', 'OK', 'close', 'ok'])
    if close_buttons:
        print(f"[ECO Automation] Found Close button: '{close_buttons[0][1]}'")
        for attempt in range(5):  # More attempts
            try:
                win32gui.SetForegroundWindow(eco_dialog)
                win32gui.BringWindowToTop(eco_dialog)
                time.sleep(0.2)
                
                if click_button(close_buttons[0][0]):
                    print("[ECO Automation] Clicked Close")
                    time.sleep(2)
                    close_clicked = True
                    break
                else:
                    print(f"[ECO Automation] Click attempt {attempt+1} failed, retrying...")
                    time.sleep(0.5)
            except Exception as e:
                print(f"[ECO Automation] Exception during Close click: {e}")
                time.sleep(0.5)
    else:
        print("[ECO Automation] Close button not found by text")
        # Try common close button patterns
        for btn in all_buttons:
            if btn[1] and ('close' in btn[1].lower() or btn[1].lower() == 'ok'):
                print(f"[ECO Automation] Found potential Close button: '{btn[1]}'")
                try:
                    win32gui.SetForegroundWindow(eco_dialog)
                    time.sleep(0.2)
                    if click_button(btn[0]):
                        print("[ECO Automation] Clicked Close")
                        time.sleep(2)
                        close_clicked = True
                        break
                except Exception as e:
                    print(f"[ECO Automation] Exception: {e}")
                    continue
    
    if close_clicked:
        print("[ECO Automation] ECO dialog automation completed successfully!")
        return True
    else:
        print("[ECO Automation] WARNING: Could not click Close button")
        print("[ECO Automation] Dialog may still be open, but changes should be executed")
        # Return True anyway if Execute was clicked
        return execute_clicked

if __name__ == '__main__':
    try:
        success = automate_eco_dialog()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[ECO Automation] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
