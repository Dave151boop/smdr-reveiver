"""Small helper to send test SMDR lines to a host/port."""
import socket
import sys
import time


def send(host: str = "127.0.0.1", port: int = 7000, count: int = 5, delay: float = 0.5):
    """Send some test SMDR lines to host:port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    try:
        for i in range(1, count + 1):
            line = f"Test SMDR line {i} at {time.time()}\r\n"
            s.sendall(line.encode("utf-8"))
            print("sent:", line.strip())
            time.sleep(delay)
    finally:
        s.close()


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 7000
    send(host, port)


if __name__ == "__main__":
    main()
