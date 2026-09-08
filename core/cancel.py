"""Cooperative cancellation helpers for long-running child processes."""

import subprocess
import threading


class OperationCancelled(RuntimeError):
    pass


def terminate_when_cancelled(process, cancel_event):
    """Terminate a child process when cancellation is requested."""
    finished = threading.Event()

    def watch():
        while not finished.wait(0.1):
            if cancel_event is not None and cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                return

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return finished, thread


def run_cancellable(cmd, *, cancel_event=None, **kwargs):
    """subprocess.run-compatible execution with cooperative cancellation."""
    process = subprocess.Popen(cmd, **kwargs)
    finished, watcher = terminate_when_cancelled(process, cancel_event)
    stdout, stderr = process.communicate()
    finished.set()
    watcher.join()
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelled("Operation cancelled by the user")
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
