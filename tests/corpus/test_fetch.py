import socket
import struct
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pytest

from fda_copilot.corpus import ecfr

TITLES = b'{"titles": [{"number": 21, "up_to_date_as_of": "2026-10-15"}]}'
OK = b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (
    len(TITLES),
    TITLES,
)


@contextmanager
def serve(replies: list[bytes | None]) -> Iterator[str]:
    listener = socket.create_server(("127.0.0.1", 0))

    def run() -> None:
        for reply in replies:
            conn, _ = listener.accept()
            conn.recv(65536)
            if reply is None:
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            else:
                conn.sendall(reply)
            conn.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    thread.join(timeout=5)
    listener.close()


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    calls: list[float] = []
    monkeypatch.setattr(ecfr.time, "sleep", calls.append)
    return calls


@pytest.mark.parametrize(
    "first",
    [
        pytest.param(b"", id="closed-before-status-line"),
        pytest.param(None, id="connection-reset"),
        pytest.param(
            b'HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\n{"titles"',
            id="incomplete-body",
        ),
        pytest.param(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n", id="503"),
    ],
)
def test_retries_a_dropped_first_connection(
    first: bytes | None, sleeps: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    with serve([first, OK]) as api:
        monkeypatch.setattr(ecfr, "API", api)

        assert ecfr.latest_date() == date(2026, 10, 15)
        assert sleeps == [1]


def test_429_waits_for_retry_after(sleeps: list[float], monkeypatch: pytest.MonkeyPatch) -> None:
    too_many = b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 7\r\nContent-Length: 0\r\n\r\n"
    with serve([too_many, OK]) as api:
        monkeypatch.setattr(ecfr, "API", api)

        assert ecfr.latest_date() == date(2026, 10, 15)
        assert sleeps == [7]


def test_404_is_not_retried(sleeps: list[float], monkeypatch: pytest.MonkeyPatch) -> None:
    with serve([b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"]) as api:
        monkeypatch.setattr(ecfr, "API", api)

        with pytest.raises(ecfr.urllib.error.HTTPError, match="404"):
            ecfr.latest_date()
        assert sleeps == []
