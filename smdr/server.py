"""Simple TCP server to receive SMDR lines and forward them via callback.

This module also exposes FIELD_NAMES — a sequence of canonical SMDR field names used
by the GUI to show column headers for received records.
"""
import socket
import threading
import logging
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)

# Canonical SMDR field names (37 items). These are used by the GUI to label
# received data columns; names are lower_snake_case and displayed via title-casing
# in the UI.
FIELD_NAMES = [
    # 1. Call Start Time
    'call_start_time',
    # 2. Connected Time
    'connected_time',
    # 3. Ring Time
    'ring_time',
    # 4. Caller
    'caller',
    # 5. Direction
    'direction',
    # 6. Called Number
    'called_number',
    # 7. Dialed Number
    'dialed_number',
    # 8. Account Code
    'account_code',
    # 9. Is Internal
    'is_internal',
    # 10. Call ID
    'call_id',
    # 11. Continuation
    'continuation',
    # 12. Party1 Device
    'party1_device',
    # 13. Party1 Name
    'party1_name',
    # 14. Party2 Device
    'party2_device',
    # 15. Party2 Name
    'party2_name',
    # 16. Hold Time
    'hold_time',
    # 17. Park Time
    'park_time',
    # 18. Authorization Valid
    'authorization_valid',
    # 19. Authorization Code
    'authorization_code',
    # 20. User Charged
    'user_charged',
    # 21. Call Charge
    'call_charge',
    # 22. Currency
    'currency',
    # 23. Amount at Last User Change
    'amount_at_last_user_change',
    # 24. Call Units
    'call_units',
    # 25. Units at Last User Change
    'units_at_last_user_change',
    # 26. Cost per Unit
    'cost_per_unit',
    # 27. Mark Up
    'mark_up',
    # 28. External Targeting Cause
    'external_targeting_cause',
    # 29. External Targeter ID
    'external_targeter_id',
    # 30. External Targeted Number
    'external_targeted_number',
    # 31. Calling Party Server IP Address
    'calling_party_server_ip_address',
    # 32. Unique Call ID for the Caller Extension
    'unique_call_id_caller_extension',
    # 33. Called Party Server IP Address
    'called_party_server_ip_address',
    # 34. Unique Call ID for the Called Extension
    'unique_call_id_called_extension',
    # 35. SMDR Record Time
    'smdr_record_time',
    # 36. Caller Consent Directive
    'caller_consent_directive',
    # 37. Calling Number Verification
    'calling_number_verification',
]


class SMDRServer:
    """A lightweight TCP server running in background threads.

    It calls the provided callback with (text, addr) for each chunk of data received.
    """

    def __init__(self, on_data: Optional[Callable[[str, Tuple[str, int]], None]] = None):
        self.on_data = on_data
        self._sock = None
        self._accept_thread = None
        self._clients = []  # list of (socket, thread)
        self._running = threading.Event()
        self.port = 7000

    def start(self, port: int = 7000):
        """Start listening on the given port.

        This method is safe to call while the server is running: it will *try* to
        bind a new socket first and only switch over if binding succeeds. That
        preserves the existing listener if the new port cannot be bound.
        """
        port = int(port)

        # Create and bind a new socket before tearing down the old one. This
        # prevents the server from stopping if the requested port is unavailable.
        new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow reusing the address to reduce 'address already in use' issues on restart
        new_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            new_sock.bind(("0.0.0.0", port))
        except Exception as e:
            # Provide a clearer error message to callers.
            new_sock.close()
            raise RuntimeError(f"Could not bind to port {port}: {e}") from e

        # If bind succeeded, finish configuring the new socket.
        try:
            new_sock.listen(5)
            actual_port = new_sock.getsockname()[1]
        except Exception:
            new_sock.close()
            raise

        # Stop the current server cleanly, then replace the socket and start
        # the accept thread for the newly bound socket.
        self.stop()
        self._sock = new_sock
        try:
            self.port = actual_port
        except Exception:
            self.port = port
        self._running.set()
        logger.info("SMDRServer listening on 0.0.0.0:%s", self.port)
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    @staticmethod
    def is_port_available(port: int) -> bool:
        """Return True if the given TCP port is free to bind on all interfaces.

        This tries to bind a short-lived socket to determine availability. On
        Windows, we attempt to use SO_EXCLUSIVEADDRUSE if available to perform
        a strict check.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Try to use exclusive bind check on Windows when available
            ex_opt = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)
            if ex_opt is not None:
                s.setsockopt(socket.SOL_SOCKET, ex_opt, 1)
            else:
                # Fall back to REUSEADDR for portability
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", int(port)))
            return True
        except Exception:
            return False
        finally:
            try:
                s.close()
            except Exception:
                pass
    def _accept_loop(self):
        while self._running.is_set():
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break
            logger.debug("Accepted connection from %s", addr)
            t = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
            t.start()
            self._clients.append((conn, t))

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]):
        with conn:
            logger.debug("Handling client %s", addr)
            while self._running.is_set():
                try:
                    data = conn.recv(4096)
                except OSError:
                    logger.debug("Connection error from %s", addr, exc_info=True)
                    break
                if not data:
                    break
                logger.debug("Received %d bytes from %s", len(data), addr)
                try:
                    text = data.decode("utf-8", errors="replace")
                except Exception:
                    logger.warning("UTF-8 decode failed for data from %s; trying latin-1", addr, exc_info=True)
                    # Fallback to latin-1 which maps raw bytes 1:1 to unicode
                    # and avoids raising during decoding.
                    try:
                        text = data.decode("latin-1", errors="replace")
                    except Exception:
                        logger.warning("latin-1 decode also failed for data from %s", addr, exc_info=True)
                        # As a last resort, use a safe representation of the raw data
                        try:
                            text = str(data)
                        except Exception:
                            text = "<undecodable data>"
                # Truncate long text in logs
                short_text = text if len(text) < 200 else text[:200] + '...'
                logger.info("Received text from %s: %r", addr, short_text)
                if self.on_data:
                    try:
                        self.on_data(text, addr)
                    except Exception:
                        logger.exception("on_data callback raised an exception for %s", addr)

    def stop(self):
        """Stop the server and close all client sockets."""
        self._running.clear()
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        # close clients
        for conn, _ in self._clients:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        self._clients = []
        # Wait for accept thread to finish; longer timeout to ensure sockets are closed.
        if self._accept_thread:
            self._accept_thread.join(timeout=2.0)
            if self._accept_thread.is_alive():
                logger.warning("SMDRServer accept thread did not terminate within timeout")
            self._accept_thread = None