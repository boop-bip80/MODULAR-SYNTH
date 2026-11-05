#!/usr/bin/env python3
"""Seed a checksum-pinned GCC Linaro source tarball for MOD's crosstool-NG.

The old releases.linaro.org GCC 7.5 URL redirects to an HTML contact page.
This tool intentionally requires an independently verified HTTPS mirror and
SHA-256: a redirect that succeeds with HTTP 200 is not a valid source archive.
"""

import argparse
import hashlib
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen


ARCHIVE_NAME = "gcc-linaro-7.5-2019.12.tar.xz"
ROOT_NAME = "gcc-linaro-7.5-2019.12"
XZ_MAGIC = b"\xfd7zXZ\x00"
MAX_SOURCE_BYTES = 1_500_000_000


class SourceArchiveError(Exception):
    """A source archive cannot safely be used by the MOD toolchain."""


def validate_sha256(value: str) -> str:
    if not re.fullmatch(r"[a-fA-F0-9]{64}", value):
        raise SourceArchiveError("MOD_LINARO_SOURCE_SHA256 must contain 64 hex characters")
    return value.lower()


def validate_https(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SourceArchiveError("MOD_LINARO_SOURCE_URL must be an HTTPS URL without embedded credentials")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive(path: Path, expected_digest: str) -> None:
    if sha256_file(path) != expected_digest:
        raise SourceArchiveError("Downloaded GCC Linaro archive SHA-256 mismatch")
    with path.open("rb") as source:
        if source.read(len(XZ_MAGIC)) != XZ_MAGIC:
            raise SourceArchiveError("Downloaded source is not XZ data (possibly a redirected HTML page)")
    try:
        with tarfile.open(path, "r:xz") as source:
            found_root = False
            members = 0
            for member in source:
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts:
                    raise SourceArchiveError("GCC Linaro tar archive contains an unsafe member path")
                if not name.parts or name.parts[0] != ROOT_NAME:
                    raise SourceArchiveError("Downloaded tar archive is not GCC Linaro 7.5-2019.12 source")
                found_root = True
                members += 1
            if not found_root or members < 2:
                raise SourceArchiveError("GCC Linaro tar archive is incomplete")
    except (tarfile.TarError, lzma.LZMAError, EOFError, OSError) as exc:
        raise SourceArchiveError("Downloaded GCC Linaro XZ/tar integrity check failed") from exc


def seed_archive(url: str, expected_digest: str, destination: Path) -> str:
    validate_https(url)
    expected_digest = validate_sha256(expected_digest)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / ARCHIVE_NAME
    if target.exists():
        try:
            validate_archive(target, expected_digest)
        except SourceArchiveError:
            pass  # Replace only after a valid new archive has been downloaded.
        else:
            return "verified cached source"

    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination, prefix=".mod-linaro-", delete=False) as temp:
            staged = Path(temp.name)
            with urlopen(url, timeout=45) as response:
                validate_https(response.geturl())
                if response.headers.get_content_type() == "text/html":
                    raise SourceArchiveError("Mirror returned HTML, not GCC Linaro source")
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_SOURCE_BYTES:
                        raise SourceArchiveError("Mirror returned an excessively large source archive")
                    temp.write(chunk)
        validate_archive(staged, expected_digest)
        os.replace(staged, target)
        return "downloaded and verified source"
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=os.environ.get("MOD_LINARO_SOURCE_URL", ""))
    parser.add_argument("--sha256", default=os.environ.get("MOD_LINARO_SOURCE_SHA256", ""))
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / "mod-workdir" / "download")
    args = parser.parse_args()
    try:
        if not args.source_url or not args.sha256:
            raise SourceArchiveError(
                "The old Linaro GCC 7.5 source URL now redirects to an HTML page. "
                "Configure repository variables MOD_LINARO_SOURCE_URL (verified HTTPS mirror) "
                "and MOD_LINARO_SOURCE_SHA256 (independently verified archive digest). "
                "MOD hardware builds remain blocked until a trusted source is available."
            )
        result = seed_archive(args.source_url, args.sha256, args.cache_dir)
        print(f"MOD GCC Linaro 7.5 source: {result}")
        return 0
    except (SourceArchiveError, OSError) as exc:
        # Do not echo potentially sensitive mirror URLs or query strings.
        print(f"MOD toolchain source preflight failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
