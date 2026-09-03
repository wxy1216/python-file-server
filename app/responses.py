from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from secrets import token_hex
from urllib.parse import quote

from anyio import open_file
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse, Response


class MalformedRangeHeader(Exception):
    def __init__(self, content: str = "Malformed range header.") -> None:
        self.content = content


class RangeNotSatisfiable(Exception):
    def __init__(self, max_size: int) -> None:
        self.max_size = max_size


class SlicedFileResponse(Response):
    chunk_size = 64 * 1024
    max_ranges = 100

    def __init__(
        self,
        chunks: Sequence[tuple[Path, int]],
        *,
        media_type: str | None = None,
        filename: str | None = None,
        etag: str | None = None,
        size: int | None = None,
    ) -> None:
        self.chunks = list(chunks)
        self.file_size = (
            size if size is not None else sum(chunk_size for _, chunk_size in self.chunks)
        )
        resolved_media_type = media_type or "application/octet-stream"
        headers = {
            "content-type": resolved_media_type,
            "content-length": str(self.file_size),
            "accept-ranges": "bytes",
        }
        if etag is not None:
            headers["etag"] = etag
        super().__init__(status_code=200, headers=headers)

        if filename is not None:
            quoted_filename = quote(filename)
            if quoted_filename != filename:
                content_disposition = (
                    f"attachment; filename*=utf-8''{quoted_filename}"
                )
            else:
                content_disposition = f'attachment; filename="{filename}"'
            self.headers.setdefault("content-disposition", content_disposition)

    async def __call__(self, scope, receive, send) -> None:
        send_header_only = (
            scope["type"] == "http" and scope["method"].upper() == "HEAD"
        )
        request_headers = Headers(scope=scope)
        range_header = request_headers.get("range")
        if_range = request_headers.get("if-range")

        if range_header is None or (
            if_range is not None and not self._should_use_range(if_range)
        ):
            await self._send_range(
                send,
                0,
                self.file_size,
                status_code=self.status_code,
                send_header_only=send_header_only,
            )
            return

        try:
            ranges = self._parse_range_header(range_header, self.file_size)
        except MalformedRangeHeader as exc:
            response = PlainTextResponse(exc.content, status_code=400)
            await response(scope, receive, send)
            return
        except RangeNotSatisfiable as exc:
            response = PlainTextResponse(
                status_code=416,
                headers={"Content-Range": f"bytes */{exc.max_size}"},
            )
            await response(scope, receive, send)
            return

        if len(ranges) == 0:
            await self._send_range(
                send,
                0,
                self.file_size,
                status_code=self.status_code,
                send_header_only=send_header_only,
            )
        elif len(ranges) == 1:
            start, end = ranges[0]
            await self._send_range(
                send,
                start,
                end,
                status_code=206,
                extra_headers={
                    "content-range": f"bytes {start}-{end - 1}/{self.file_size}",
                    "content-length": str(end - start),
                },
                send_header_only=send_header_only,
            )
        else:
            await self._send_multiple_ranges(
                send,
                ranges,
                send_header_only=send_header_only,
            )

    async def _send_range(
        self,
        send,
        start: int,
        end: int,
        *,
        status_code: int,
        extra_headers: dict[str, str] | None = None,
        send_header_only: bool,
    ) -> None:
        headers = MutableHeaders(raw=list(self.raw_headers))
        if extra_headers:
            for key, value in extra_headers.items():
                headers[key] = value
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": headers.raw,
            }
        )
        if send_header_only:
            await send(
                {"type": "http.response.body", "body": b"", "more_body": False}
            )
            return
        async for body in self._iter_bytes(start, end):
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                    "more_body": True,
                }
            )
        await send(
            {"type": "http.response.body", "body": b"", "more_body": False}
        )

    async def _send_multiple_ranges(
        self,
        send,
        ranges: list[tuple[int, int]],
        *,
        send_header_only: bool,
    ) -> None:
        boundary = token_hex(13)
        content_type = self.headers.get("content-type", "application/octet-stream")
        content_length, header_generator = self._generate_multipart(
            ranges,
            boundary,
            self.file_size,
            content_type,
        )
        headers = MutableHeaders(raw=list(self.raw_headers))
        headers["content-type"] = f"multipart/byteranges; boundary={boundary}"
        headers["content-length"] = str(content_length)
        await send(
            {
                "type": "http.response.start",
                "status": 206,
                "headers": headers.raw,
            }
        )
        if send_header_only:
            await send(
                {"type": "http.response.body", "body": b"", "more_body": False}
            )
            return
        for start, end in ranges:
            await send(
                {
                    "type": "http.response.body",
                    "body": header_generator(start, end),
                    "more_body": True,
                }
            )
            async for body in self._iter_bytes(start, end):
                await send(
                    {
                        "type": "http.response.body",
                        "body": body,
                        "more_body": True,
                    }
                )
            await send(
                {"type": "http.response.body", "body": b"\r\n", "more_body": True}
            )
        await send(
            {
                "type": "http.response.body",
                "body": f"--{boundary}--".encode("latin-1"),
                "more_body": False,
            }
        )

    async def _iter_bytes(self, start: int, end: int) -> AsyncIterator[bytes]:
        if start >= end:
            return
        cursor = 0
        for path, chunk_size in self.chunks:
            if end <= cursor:
                return
            chunk_end = min(end, cursor + chunk_size)
            if chunk_end > start:
                local_start = max(start - cursor, 0)
                length = chunk_end - max(start, cursor)
                async with await open_file(path, "rb") as file:
                    await file.seek(local_start)
                    remaining = length
                    while remaining > 0:
                        body = await file.read(min(self.chunk_size, remaining))
                        if not body:
                            raise RuntimeError(f"chunk file truncated: {path}")
                        remaining -= len(body)
                        yield body
            cursor += chunk_size

    def _should_use_range(self, if_range: str) -> bool:
        return if_range == self.headers.get("last-modified") or if_range == self.headers.get(
            "etag"
        )

    @classmethod
    def _parse_range_header(
        cls,
        range_header: str,
        file_size: int,
    ) -> list[tuple[int, int]]:
        try:
            units, range_value = range_header.split("=", 1)
        except ValueError:
            raise MalformedRangeHeader()

        if units.strip().lower() != "bytes":
            raise MalformedRangeHeader("Only support bytes range")

        if range_value.count(",") + 1 > cls.max_ranges:
            return []

        ranges = cls._parse_ranges(range_value, file_size)
        if len(ranges) == 0:
            raise MalformedRangeHeader("Range header: range must be requested")
        if any(not (0 <= start < file_size) for start, _ in ranges):
            raise RangeNotSatisfiable(file_size)
        if any(start >= end for start, end in ranges):
            raise MalformedRangeHeader("Range header: start must be less than end")

        if len(ranges) == 1:
            return ranges

        ranges.sort()
        merged: list[tuple[int, int]] = [ranges[0]]
        for start, end in ranges[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    @classmethod
    def _parse_ranges(
        cls,
        range_value: str,
        file_size: int,
    ) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        for part in range_value.split(","):
            part = part.strip()
            if not part or part == "-":
                continue
            if "-" not in part:
                continue
            start_str, end_str = part.split("-", 1)
            start_str = start_str.strip()
            end_str = end_str.strip()
            try:
                if start_str:
                    start = int(start_str)
                else:
                    start = max(file_size - int(end_str), 0)
                if start_str and end_str and int(end_str) < file_size:
                    end = int(end_str) + 1
                else:
                    end = file_size
                ranges.append((start, end))
            except ValueError:
                continue
        return ranges

    def _generate_multipart(
        self,
        ranges: Sequence[tuple[int, int]],
        boundary: str,
        max_size: int,
        content_type: str,
    ) -> tuple[int, Callable[[int, int], bytes]]:
        boundary_len = len(boundary)
        static_header_part_len = (
            49 + boundary_len + len(content_type) + len(str(max_size))
        )
        content_length = sum(
            (len(str(start)) + len(str(end - 1)) + static_header_part_len)
            + (end - start)
            for start, end in ranges
        ) + (4 + boundary_len)
        return (
            content_length,
            lambda start, end: (
                f"""\
--{boundary}\r
Content-Type: {content_type}\r
Content-Range: bytes {start}-{end - 1}/{max_size}\r
\r
"""
            ).encode("latin-1"),
        )
