"""Run a short end-to-end test: start SMDRServer, send a line, and show received text."""
from smdr.server import SMDRServer
import socket
import time


def on_data(text, addr):
    print("RECV:", repr(text))


if __name__ == '__main__':
    srv = SMDRServer(on_data=on_data)
    srv.start(0)
    print("Started server on port", srv.port)
    # send a test SMDR line
    c = socket.create_connection(("127.0.0.1", srv.port), timeout=1)
    c.sendall(b"TestSMDRLine1,field2,field3\r\n")
    c.close()
    # allow callback to run
    time.sleep(0.5)
    srv.stop()
    print("Server stopped")
