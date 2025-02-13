import threading
import time
from typing import Dict, Set
from datetime import datetime, timedelta

class ThreadMonitor:
    def __init__(self):
        self.active_threads: Dict[int, Dict] = {}  # lecture_id -> thread info
        self.lock = threading.Lock()
        self._monitor_thread = None
        self._stop_monitoring = False
    
    def start_monitoring(self):
        """Start the monitoring thread"""
        if not self._monitor_thread:
            self._stop_monitoring = False
            self._monitor_thread = threading.Thread(target=self._monitor_threads, daemon=True)
            self._monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop the monitoring thread"""
        self._stop_monitoring = True
        if self._monitor_thread:
            self._monitor_thread.join()
            self._monitor_thread = None
    
    def register_thread(self, lecture_id: int, thread: threading.Thread):
        """Register a new content generation thread"""
        with self.lock:
            self.active_threads[lecture_id] = {
                'thread': thread,
                'start_time': datetime.now(),
                'last_progress': datetime.now()
            }
    
    def update_progress(self, lecture_id: int):
        """Update the last progress time for a thread"""
        with self.lock:
            if lecture_id in self.active_threads:
                self.active_threads[lecture_id]['last_progress'] = datetime.now()
    
    def unregister_thread(self, lecture_id: int):
        """Remove a thread from monitoring"""
        with self.lock:
            if lecture_id in self.active_threads:
                del self.active_threads[lecture_id]
    
    def _monitor_threads(self):
        """Monitor thread for checking stalled threads"""
        while not self._stop_monitoring:
            try:
                stalled_threads = set()
                with self.lock:
                    now = datetime.now()
                    for lecture_id, info in self.active_threads.items():
                        # Check if thread is alive and hasn't made progress in 5 minutes
                        if (not info['thread'].is_alive() or 
                            (now - info['last_progress']) > timedelta(minutes=5)):
                            stalled_threads.add(lecture_id)
                
                # Handle stalled threads
                for lecture_id in stalled_threads:
                    self._handle_stalled_thread(lecture_id)
                
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                print(f"Error in thread monitor: {str(e)}")
    
    def _handle_stalled_thread(self, lecture_id: int):
        """Handle a stalled thread"""
        try:
            with self.lock:
                if lecture_id in self.active_threads:
                    info = self.active_threads[lecture_id]
                    # Send error message through progress queue
                    if lecture_id in progress_queues:
                        progress_queues[lecture_id].put({
                            'component': 'error',
                            'progress': 'Content generation process has stalled'
                        })
                    # Clean up
                    self.unregister_thread(lecture_id)
        except Exception as e:
            print(f"Error handling stalled thread for lecture {lecture_id}: {str(e)}")

# Global thread monitor instance
thread_monitor = ThreadMonitor()
thread_monitor.start_monitoring()