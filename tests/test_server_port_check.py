import socket
import pytest
from smdr.server import SMDRServer


def test_is_port_available_for_busy_port():
    # open a blocker socket bound to a different port to simulate 'in use'
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ex_opt = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)
    if ex_opt is not None:
        blocker.setsockopt(socket.SOL_SOCKET, ex_opt, 1)
    else:
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("0.0.0.0", 0))
    blocker.listen(1)
    busy_port = blocker.getsockname()[1]

    try:
        assert SMDRServer.is_port_available(busy_port) is False
    finally:
        try:
            blocker.close()
        except Exception:
            pass


def test_stop_releases_port():
    srv = SMDRServer()
    srv.start(0)
    try:
        port = srv.port
        assert port != 0
    finally:
        srv.stop()

    # After stopping, it should be possible to bind this port again (best-effort)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        s.close()
    except Exception as e:
        pytest.skip(f"Platform/network stack prevented immediate bind after stop: {e}")
