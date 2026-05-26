#!/usr/bin/env python3
"""
Robust server launcher that keeps the SecureFlow server running.
Monitors health, auto-restarts on failure, provides lifecycle management.
"""

import subprocess
import time
import psutil
import os
import sys
import signal
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

class ServerManager:
    """Manage server lifecycle with auto-restart and health checks."""

    def __init__(self, venv_path: str = "/home/sky/secureflow/venv"):
        self.venv_path = Path(venv_path)
        self.python_exe = self.venv_path / "bin" / "python"
        self.server_module = "secureflow.server"
        self.port = 5000
        self.process = None
        self.last_restart = None
        self.restart_count = 0
        self.should_run = True

    def verify_server_ready(self, timeout: int = 10) -> bool:
        """Verify server is responding to health checks."""
        import requests
        start = time.time()
        while time.time() - start < timeout:
            try:
                response = requests.get(
                    f"http://localhost:{self.port}/ui",
                    timeout=2
                )
                if response.status_code < 500:
                    logger.info("✅ Server responding on health check")
                    return True
            except Exception as e:
                logger.debug(f"Health check failed: {e}")
            time.sleep(1)

        logger.error(f"❌ Server not responding after {timeout}s")
        return False

    def is_process_alive(self) -> bool:
        """Check if server process is still running."""
        if not self.process:
            return False
        if self.process.poll() is not None:
            return False
        try:
            proc = psutil.Process(self.process.pid)
            return proc.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def start_server(self) -> bool:
        """Start the server process."""
        logger.info("=" * 60)
        logger.info("Starting SecureFlow Server...")
        logger.info("=" * 60)

        try:
            self.process = subprocess.Popen(
                [str(self.python_exe), "-m", self.server_module],
                cwd=str(self.venv_path.parent),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            logger.info(f"Server process started (PID: {self.process.pid})")

            # Give it a moment to initialize
            time.sleep(2)

            # Verify it actually started
            if not self.is_process_alive():
                logger.error("❌ Server process died immediately after start")
                stdout, stderr = self.process.communicate(timeout=1)
                logger.error(f"Server stdout:\n{stdout}")
                logger.error(f"Server stderr:\n{stderr}")
                return False

            # Check if it's responding
            if not self.verify_server_ready(timeout=10):
                logger.warning("Server process running but not responding")
                self.kill_process()
                return False

            logger.info("✅ Server started and responding")
            self.restart_count += 1
            self.last_restart = datetime.now()
            return True

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False

    def kill_process(self):
        """Forcefully terminate server process."""
        if not self.process:
            return

        try:
            logger.info(f"Stopping process {self.process.pid}...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
                logger.info("Process terminated gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("Process didn't terminate, forcing kill...")
                self.process.kill()
                self.process.wait()
                logger.info("Process killed")
        except Exception as e:
            logger.error(f"Error stopping process: {e}")

    def monitor_loop(self):
        """Main monitoring loop - restart if server dies."""
        logger.info("Entering monitor loop...")
        consecutive_failures = 0
        max_consecutive_failures = 3

        while self.should_run:
            # Check if server is alive
            if self.is_process_alive():
                consecutive_failures = 0
                logger.info(f"✅ Server healthy (PID: {self.process.pid})")
                time.sleep(10)  # Check every 10 seconds
            else:
                consecutive_failures += 1
                logger.warning(f"❌ Server not responding (failure #{consecutive_failures})")

                if consecutive_failures >= max_consecutive_failures:
                    logger.info(f"Restart #{self.restart_count + 1} (failures: {consecutive_failures})")
                    self.kill_process()

                    # Exponential backoff: 2s, 4s, 8s
                    backoff = min(2 ** consecutive_failures, 30)
                    logger.info(f"Waiting {backoff}s before restart...")
                    time.sleep(backoff)

                    if not self.start_server():
                        consecutive_failures += 1
                        if consecutive_failures > 10:
                            logger.error("Max restarts exceeded. Giving up.")
                            self.should_run = False
                            break

                time.sleep(5)  # Check more frequently while restarting

    def run(self):
        """Main entry point - start server and monitor."""
        # Setup signal handlers
        def signal_handler(signum, frame):
            logger.info("Received shutdown signal, cleaning up...")
            self.should_run = False
            self.kill_process()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Initial startup
        max_initial_attempts = 3
        for attempt in range(max_initial_attempts):
            if self.start_server():
                break
            if attempt < max_initial_attempts - 1:
                logger.info(f"Retry {attempt + 1}/{max_initial_attempts - 1}...")
                time.sleep(5)
        else:
            logger.error("Failed to start server after max attempts")
            sys.exit(1)

        # Monitor loop
        try:
            self.monitor_loop()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            logger.info("Shutting down server manager...")
            self.kill_process()
            logger.info("=" * 60)
            logger.info(f"Total restarts: {self.restart_count}")
            logger.info("Server manager stopped")
            logger.info("=" * 60)


def main():
    """Entry point."""
    import sys

    venv_path = os.getenv("VENV_PATH", "/home/sky/secureflow/venv")

    if not Path(venv_path).exists():
        print(f"ERROR: venv not found at {venv_path}")
        sys.exit(1)

    manager = ServerManager(venv_path)
    manager.run()


if __name__ == "__main__":
    main()
