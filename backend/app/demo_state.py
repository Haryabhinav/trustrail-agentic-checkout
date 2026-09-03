"""In-memory fault injection for the live failure-recovery demo.

Deliberately process-local, non-persistent state — this is a demo control knob, not
production config. Reset on restart, which is exactly what you want between demo runs.
"""
import threading

_lock = threading.Lock()
_remaining_failures = 0


class SimulatedGatewayError(Exception):
    """Raised in place of a real Razorpay 5xx when the demo fault injector is armed."""


def arm(attempts: int) -> None:
    global _remaining_failures
    with _lock:
        _remaining_failures = max(0, attempts)


def maybe_fail() -> None:
    """Call this immediately before every create_order attempt."""
    global _remaining_failures
    with _lock:
        if _remaining_failures > 0:
            _remaining_failures -= 1
            raise SimulatedGatewayError("simulated Razorpay 502 (demo fault injection armed)")


def status() -> int:
    with _lock:
        return _remaining_failures
