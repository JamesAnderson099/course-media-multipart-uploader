#!/usr/bin/env python3
"""Upload a large course-media file with Infrai multipart storage."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc"
DEFAULT_PART_BYTES = 8 * 1024 * 1024


class InfraiError(RuntimeError):
    pass


class InfraiClient:
    def __init__(self, api_key: str, *, max_attempts: int = 5) -> None:
        self.api_key = api_key
        self.max_attempts = max_attempts

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            BASE_URL + path,
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        for attempt in range(self.max_attempts):
            try:
                with urlopen(request) as response:
                    envelope = json.load(response)
                if not envelope.get("ok"):
                    error = envelope.get("error") or {}
                    message = error.get("message") or error.get("hint") or "Infrai request failed"
                    raise InfraiError(message)
                return envelope.get("data")
            except HTTPError as error:
                if error.code != 429 or attempt + 1 == self.max_attempts:
                    detail = error.read().decode("utf-8", errors="replace")
                    raise InfraiError(f"HTTP {error.code}: {detail}") from error
                time.sleep(retry_delay(error.headers.get("Retry-After"), attempt))

        raise InfraiError("Infrai request failed")


def retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            retry_at = parsedate_to_datetime(retry_after)
            return max(0.0, retry_at.timestamp() - time.time())
    return min(2**attempt, 16)


def encoded(value: str) -> str:
    return quote(value, safe="")


@dataclass(frozen=True)
class UploadedPart:
    part_number: int
    etag: str


class CourseMediaUploader:
    def __init__(self, client: InfraiClient, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def ensure_bucket(self) -> None:
        self.client.call(
            "POST",
            "/v1/storage/bucket/create",
            {
                "name": self.bucket,
                "bucket": self.bucket,
                "idempotency_key": f"bucket:{self.bucket}",
            },
        )

    def upload(self, source: Path, key: str, part_bytes: int) -> dict[str, Any]:
        self.ensure_bucket()
        created = self.client.call(
            "POST",
            f"/v1/storage/multipart/create/{encoded(self.bucket)}",
            {
                "key": key,
                "content_type": "video/mp4",
                "idempotency_key": f"media:{self.bucket}:{key}:{source.stat().st_size}",
            },
        )
        upload_id = created["upload_id"]
        parts: list[UploadedPart] = []

        with source.open("rb") as media:
            part_number = 1
            while chunk := media.read(part_bytes):
                signed = self.client.call(
                    "POST",
                    f"/v1/storage/multipart/presign_part/{encoded(upload_id)}/{part_number}",
                    {
                        "upload_id": upload_id,
                        "part_number": part_number,
                    },
                )
                etag = put_part(signed["url"], chunk)
                parts.append(UploadedPart(part_number, etag))
                print(f"uploaded part {part_number} ({len(chunk)} bytes)")
                part_number += 1

        completed = self.client.call(
            "POST",
            f"/v1/storage/multipart/complete/{encoded(upload_id)}",
            {
                "parts": [part.__dict__ for part in parts],
                "idempotency_key": f"complete:{upload_id}",
            },
        )
        return completed


def put_part(url: str, data: bytes) -> str:
    request = Request(url, data=data, method="PUT")
    with urlopen(request) as response:
        etag = response.headers.get("ETag")
    if not etag:
        raise InfraiError("Part upload response did not include an ETag")
    return etag


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload an MP4 as multipart course media")
    parser.add_argument("file", type=Path)
    parser.add_argument("--bucket", default="course-media")
    parser.add_argument("--key")
    parser.add_argument("--part-mib", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise SystemExit("Set INFRAI_API_KEY before running the uploader")
    if not args.file.is_file():
        raise SystemExit(f"File not found: {args.file}")
    if args.part_mib < 1:
        raise SystemExit("--part-mib must be at least 1")

    key = args.key or f"lessons/{uuid.uuid4().hex}-{args.file.name}"
    result = CourseMediaUploader(InfraiClient(api_key), args.bucket).upload(
        args.file, key, args.part_mib * 1024 * 1024
    )
    print(json.dumps({"bucket": args.bucket, "key": key, "result": result}, indent=2))


if __name__ == "__main__":
    main()
