import socket
import threading
import time

from smdr.server import SMDRServer


def test_server_receives_data():
    received = []
    ev = threading.Event()

    def on_data(text, addr):
        received.append((text, addr))
        ev.set()

    srv = SMDRServer(on_data=on_data)
    # bind to ephemeral port
    srv.start(0)
    try:
        port = srv.port
        assert port != 0
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        try:
            s.sendall(b"Hello SMDR\r\n")
        finally:
            s.close()

        # wait for callback
        assert ev.wait(1.0), "Server did not invoke callback in time"
        assert any("Hello SMDR" in text for text, _ in received)
    finally:
        srv.stop()


def test_server_multiple_lines():
    lines = []
    ev = threading.Event()

    def on_data(text, addr):
        lines.extend(text.splitlines())
        ev.set()

    srv = SMDRServer(on_data=on_data)
    srv.start(0)
    try:
        port = srv.port
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        try:
            s.sendall(b"Line1\r\nLine2\r\n")
        finally:
            s.close()
        assert ev.wait(1.0)
        assert "Line1" in lines and "Line2" in lines
    finally:
        srv.stop()


def test_decode_fallback_on_exception():
    received = []
    ev = threading.Event()

    def on_data(text, addr):
        received.append(text)
        ev.set()

    srv = SMDRServer(on_data=on_data)

    class BadBytes:
        def __len__(self):
            return 1
        def decode(self, encoding='utf-8', errors='strict'):
            # Simulate a failure decoding as UTF-8 but succeed for latin-1
            if encoding == 'utf-8':
                raise RuntimeError("boom")
            return 'fallback'
        def __repr__(self):
            return "<BadBytes>"

    class FakeConn:
        def __init__(self, items):
            self.items = items
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            pass
        def recv(self, n):
            return self.items.pop(0) if self.items else b''
        def close(self):
            pass
        def shutdown(self, how):
            pass

    fake = FakeConn([BadBytes()])
    t = threading.Thread(target=srv._handle_client, args=(fake, ('127.0.0.1', 1234)), daemon=True)
    srv._running.set()
    t.start()
    assert ev.wait(1.0), "Fallback decoding did not trigger callback"
    assert any('fallback' in text for text in received), f"Unexpected received data: {received}"
    srv._running.clear()
    t.join(timeout=0.5)


def test_logging_emits_on_receive(caplog):
    import logging
    caplog.set_level(logging.DEBUG)

    srv = SMDRServer()
    srv.start(0)
    try:
        port = srv.port
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        try:
            s.sendall(b"LogLine\r\n")
        finally:
            s.close()
        # allow logs to be recorded
        import time
        time.sleep(0.1)
        msgs = [r.getMessage() for r in caplog.records]
        assert any("Received text" in m or "Received" in m for m in msgs), f"No expected log messages found: {msgs}"
    finally:
        srv.stop()


def test_start_does_not_stop_when_port_unavailable():
    import socket
    # start a server on an ephemeral port
    srv = SMDRServer()
    srv.start(0)
    try:
        active_port = srv.port
        # open a temporary socket bound to a different port to simulate 'in use'
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # On Windows, set SO_EXCLUSIVEADDRUSE to ensure the port cannot be rebound.
        ex_opt = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)
        if ex_opt is not None:
            blocker.setsockopt(socket.SOL_SOCKET, ex_opt, 1)
        else:
            # fallback - set SO_REUSEADDR for portability, behavior may vary by OS
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("0.0.0.0", 0))
        busy_port = blocker.getsockname()[1]
        blocker.listen(1)

        # attempt to start on the busy port; should raise on platforms that enforce exclusivity
        import pytest
        if getattr(socket, 'SO_EXCLUSIVEADDRUSE', None) is None:
            # best-effort: if exclusive option isn't available, we skip the strict assert
            pytest.skip("Platform does not support exclusive bind; skipping 'port unavailable' assertion")
        with pytest.raises(RuntimeError):
            srv.start(busy_port)

        # the original server should still accept connections
        s = socket.create_connection(("127.0.0.1", active_port), timeout=1)
        try:
            s.sendall(b"StillUp\r\n")
        finally:
            s.close()
    finally:
        try:
            blocker.close()
        except Exception:
            pass
        srv.stop()
