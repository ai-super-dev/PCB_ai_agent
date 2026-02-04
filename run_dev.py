"""
Development mode with auto-reload
Watches for file changes and automatically restarts the application
Similar to FastAPI's --reload flag
"""
import subprocess
import sys
import time
import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AppReloadHandler(FileSystemEventHandler):
    """Handles file system events to trigger app reload"""
    
    def __init__(self, restart_callback):
        super().__init__()
        self.restart_callback = restart_callback
        self.last_modified = time.time()
        self.debounce_time = 0.5  # Wait 0.5 seconds before reloading
        
    def on_modified(self, event):
        """Called when a file is modified"""
        if event.is_directory:
            return
        
        # Only watch Python files
        if not event.src_path.endswith('.py'):
            return
        
        # Ignore changes in __pycache__ and venv
        if '__pycache__' in event.src_path or 'venv' in event.src_path:
            return
        
        current_time = time.time()
        # Debounce: ignore rapid successive changes
        if current_time - self.last_modified < self.debounce_time:
            return
        
        self.last_modified = current_time
        print(f"\n[Auto-Reload] File changed: {event.src_path}")
        print("[Auto-Reload] Restarting application...")
        self.restart_callback()

class AutoReloadApp:
    """Manages application with auto-reload"""
    
    def __init__(self):
        self.process = None
        self.observer = None
        self.running = True
        
    def start_app(self):
        """Start the application"""
        if self.process and self.process.poll() is None:
            # Process is still running, kill it first
            print("[Auto-Reload] Stopping current instance...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        
        print("[Auto-Reload] Starting application...")
        self.process = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=os.getcwd()
        )
    
    def restart_app(self):
        """Restart the application"""
        self.start_app()
    
    def start_watcher(self):
        """Start watching for file changes"""
        event_handler = AppReloadHandler(self.restart_app)
        self.observer = Observer()
        
        # Watch current directory and subdirectories (except venv, __pycache__)
        watch_paths = [
            '.',  # Current directory
            'pages',
            'altium_scripts'
        ]
        
        for path in watch_paths:
            if os.path.exists(path):
                self.observer.schedule(event_handler, path, recursive=True)
                print(f"[Auto-Reload] Watching: {os.path.abspath(path)}")
        
        self.observer.start()
        print("\n" + "="*60)
        print("🚀 Development Mode - Auto-Reload Enabled")
        print("="*60)
        print("Watching for file changes...")
        print("Press Ctrl+C to stop")
        print("="*60 + "\n")
    
    def run(self):
        """Run the application with auto-reload"""
        try:
            # Start watching
            self.start_watcher()
            
            # Start the app
            self.start_app()
            
            # Keep running
            while self.running:
                if self.process:
                    # Check if process died
                    if self.process.poll() is not None:
                        print("\n[Auto-Reload] Application exited. Restarting...")
                        time.sleep(1)
                        self.start_app()
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n[Auto-Reload] Stopping...")
            self.stop()
    
    def stop(self):
        """Stop the watcher and application"""
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        print("[Auto-Reload] Stopped")

if __name__ == "__main__":
    app = AutoReloadApp()
    app.run()

