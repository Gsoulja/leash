"""Tiny local HTTP/1.1 servers for transport tests (LEASH-136).

Real sockets, because the properties under test are socket properties: whether a connection is reused,
whether a pooled socket outlives the loop it was opened on, and whether a request body is written more
than once. An in-memory ASGI transport owns no socket and cannot show any of them.
"""

import asyncio
import contextlib


def _content_length(head: bytes) -> int:
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            return int(line.split(b":")[1])
    return 0


class CountingServer:
    """Keeps connections alive and counts how many TCP connections were accepted."""

    def __init__(self, delay: float = 0.0) -> None:
        self.connections = 0
        self.requests = 0
        self.delay = delay  # holds the connection open, so a bounded pool really is exhausted
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> str:
        self._server = await asyncio.start_server(self._serve, host="127.0.0.1", port=0)
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        try:
            while True:  # keep-alive: serve request after request on the same socket
                head = await reader.readuntil(b"\r\n\r\n")
                if not head:
                    return
                length = _content_length(head)
                if length:
                    await reader.readexactly(length)
                self.requests += 1
                if self.delay:
                    await asyncio.sleep(self.delay)
                body = b'{"ok": true}'
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                             b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                             b"Connection: keep-alive\r\n\r\n" + body)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.CancelledError):
            return
        finally:
            with contextlib.suppress(Exception):
                writer.close()


class HangsUpAfterReadingTheBody(CountingServer):
    """Accepts, reads the whole request body, then closes without answering.

    The failure therefore happens *after* the body has been written, which is the case that would
    corrupt a payment if the transport replayed it.
    """

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            length = _content_length(head)
            if length:
                await reader.readexactly(length)
            self.requests += 1
        except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.CancelledError):
            return
        finally:
            with contextlib.suppress(Exception):
                writer.close()


@contextlib.asynccontextmanager
async def serving(delay: float = 0.0, server: CountingServer | None = None):
    server = server or CountingServer(delay)
    base = await server.start()
    try:
        yield server, base
    finally:
        await server.stop()
