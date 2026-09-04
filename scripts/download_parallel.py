#!/usr/bin/env python3
"""Download a file with parallel HTTP Range requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
IO_CHUNK_SIZE = 1024 * 1024


def _auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"X-API-Token": token}


def _read_json(url: str, token: str | None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=_auth_headers(token))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
        raise RuntimeError(
            f"HTTP {exc.code}: {payload.get('msg', 'unknown error')}"
        ) from exc

    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg", "unknown error"))
    return payload


def get_file_metadata(
    base_url: str,
    file_id: int,
    token: str | None,
) -> dict[str, Any]:
    payload = _read_json(f"{base_url}/api/files/{file_id}", token)
    return payload["data"]


def _build_ranges(
    total_size: int,
    threads: int,
    range_size: int | None,
) -> list[tuple[int, int]]:
    if total_size == 0:
        return []
    if range_size is None:
        part_size = max(1, math.ceil(total_size / max(1, threads)))
    else:
        part_size = range_size
    part_count = math.ceil(total_size / part_size)

    ranges: list[tuple[int, int]] = []
    for index in range(part_count):
        start = index * part_size
        end = min(start + part_size, total_size)
        ranges.append((start, end))
    return ranges


def _download_range(
    base_url: str,
    file_id: int,
    token: str | None,
    start: int,
    end: int,
    output_path: Path,
    retries: int,
) -> tuple[int, int, int]:
    expected_size = end - start
    headers = _auth_headers(token)
    headers["Range"] = f"bytes={start}-{end - 1}"
    url = f"{base_url}/api/files/{file_id}/download"

    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 206:
                    raise RuntimeError(
                        f"expected 206 but got {response.status} "
                        f"for bytes={start}-{end - 1}"
                    )
                content_range = response.headers.get("Content-Range", "")
                match = CONTENT_RANGE_RE.match(content_range)
                if match is None:
                    raise RuntimeError(f"invalid Content-Range: {content_range!r}")
                parsed_start, parsed_end, _ = map(int, match.groups())
                if parsed_start != start or parsed_end != end - 1:
                    raise RuntimeError(f"unexpected Content-Range: {content_range}")

                written = 0
                with output_path.open("r+b") as output:
                    output.seek(start)
                    while chunk := response.read(IO_CHUNK_SIZE):
                        output.write(chunk)
                        written += len(chunk)
                if written != expected_size:
                    raise RuntimeError(
                        f"range {start}-{end - 1} downloaded {written} bytes, "
                        f"expected {expected_size}"
                    )
            return start, end, written
        except Exception as exc:
            if attempt == retries:
                raise RuntimeError(f"range {start}-{end - 1} failed: {exc}") from exc
            time.sleep(attempt)

    raise RuntimeError(f"range {start}-{end - 1} failed")  # pragma: no cover


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(IO_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("PFS_BASE_URL", "http://127.0.0.1:8000"),
        help="file server base URL",
    )
    parser.add_argument("--file-id", type=int, required=True)
    parser.add_argument("-o", "--output", help="output file path")
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=4,
        help="max parallel HTTP requests",
    )
    parser.add_argument(
        "--range-size",
        type=int,
        help="fixed byte range size; defaults to threads count",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="retry count for each range",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("PFS_API_TOKEN"),
        help="X-API-Token value",
    )
    parser.add_argument("--no-verify", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base_url = args.base_url.rstrip("/")
    token = args.token

    metadata = get_file_metadata(base_url, args.file_id, token)
    file_size = int(metadata["size"])
    output = Path(args.output or metadata["original_name"])
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.threads < 1:
        print("--threads must be >= 1", file=sys.stderr)
        return 2
    if args.range_size is not None and args.range_size < 1:
        print("--range-size must be >= 1", file=sys.stderr)
        return 2

    ranges = _build_ranges(file_size, args.threads, args.range_size)
    if file_size > 0 and not ranges:
        print(
            f"invalid range config: size={file_size} threads={args.threads}",
            file=sys.stderr,
        )
        return 2

    temp_path: Path | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".download",
            dir=str(output.parent),
        )
        temp_path = Path(temp_name)
        os.ftruncate(fd, file_size)
        os.close(fd)

        started_at = time.monotonic()
        if file_size > 0:
            workers = min(args.threads, len(ranges))
            print(
                f"downloading {metadata['original_name']}: "
                f"{file_size} bytes in {len(ranges)} ranges with {workers} workers"
            )
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        _download_range,
                        base_url,
                        args.file_id,
                        token,
                        start,
                        end,
                        temp_path,
                        args.retries,
                    ): (start, end)
                    for start, end in ranges
                }
                for future in as_completed(futures):
                    start, end, _ = future.result()
                    print(f"done {start}-{end - 1} ({end - start} bytes)")

        if not args.no_verify:
            actual_sha256 = _sha256(temp_path)
            expected_sha256 = metadata["sha256"]
            if actual_sha256 != expected_sha256:
                raise RuntimeError(
                    f"sha256 mismatch: expected {expected_sha256}, got {actual_sha256}"
                )
            print(f"sha256 ok: {actual_sha256}")

        os.replace(temp_path, output)
        temp_path = None
        elapsed = time.monotonic() - started_at
        print(f"saved {output} in {elapsed:.2f}s")
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
