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
import posixpath
import re
import shutil
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ARCHIVE_NAME = "gcc-linaro-7.5-2019.12.tar.xz"
ROOT_NAME = "gcc-linaro-7.5-2019.12"
XZ_MAGIC = b"\xfd7zXZ\x00"
MAX_SOURCE_BYTES = 1_500_000_000
MAX_ARCHIVE_MEMBERS = 750_000
MAX_UNPACKED_BYTES = 12_000_000_000
MAX_MEMBER_PATH_BYTES = 4096
# The crosstool-NG source package is GCC source, not a prebuilt cross-compiler,
# a tiny redirect stub, or an unrelated archive renamed by a mirror. These
# canonical GCC 7 source files are part of the intended extraction contract.
REQUIRED_GCC_SOURCE_FILES = frozenset({
    f"{ROOT_NAME}/configure",
    f"{ROOT_NAME}/gcc/config.gcc",
    f"{ROOT_NAME}/libgcc/config.host",
})


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
    if parsed.path.rsplit("/", 1)[-1] != ARCHIVE_NAME:
        raise SourceArchiveError(
            f"MOD_LINARO_SOURCE_URL and its redirects must name {ARCHIVE_NAME}, "
            "not an HTML page or another download"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive(path: Path, expected_digest: str) -> None:
    if not 0 < path.stat().st_size <= MAX_SOURCE_BYTES:
        raise SourceArchiveError("GCC Linaro source archive violates the compressed size bound")
    if sha256_file(path) != expected_digest:
        raise SourceArchiveError("Downloaded GCC Linaro archive SHA-256 mismatch")
    with path.open("rb") as source:
        if source.read(len(XZ_MAGIC)) != XZ_MAGIC:
            raise SourceArchiveError("Downloaded source is not XZ data (possibly a redirected HTML page)")
    try:
        with tarfile.open(path, "r:xz") as source:
            members = 0
            unpacked_bytes = 0
            seen_member_paths = set()
            required_found = set()
            for member in source:
                name = PurePosixPath(member.name)
                if (
                    name.is_absolute() or ".." in name.parts or "\\" in member.name
                    or len(member.name.encode("utf-8", errors="replace")) > MAX_MEMBER_PATH_BYTES
                ):
                    raise SourceArchiveError("GCC Linaro tar archive contains an unsafe member path")
                if not name.parts or name.parts[0] != ROOT_NAME:
                    raise SourceArchiveError("Downloaded tar archive is not GCC Linaro 7.5-2019.12 source")
                # GNU tar extraction collapses redundant path separators and
                # dot components; compare the extracted target, not raw text.
                canonical_name = posixpath.normpath(member.name)
                if canonical_name in seen_member_paths:
                    raise SourceArchiveError("GCC Linaro tar archive contains a duplicate member path")
                seen_member_paths.add(canonical_name)
                members += 1
                if members > MAX_ARCHIVE_MEMBERS:
                    raise SourceArchiveError("GCC Linaro tar archive exceeds its member limit")
                if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
                    raise SourceArchiveError("GCC Linaro tar archive contains an unsafe special member")
                if member.issym() or member.islnk():
                    link = member.linkname
                    if (
                        not link or posixpath.isabs(link) or "\\" in link
                        or len(link.encode("utf-8", errors="replace")) > MAX_MEMBER_PATH_BYTES
                    ):
                        raise SourceArchiveError("GCC Linaro tar archive contains an unsafe link")
                    # Symbolic links resolve relative to their containing
                    # directory; tar hard-links resolve from archive root.
                    target = posixpath.normpath(
                        posixpath.join(posixpath.dirname(member.name), link)
                        if member.issym() else link
                    )
                    if target != ROOT_NAME and not target.startswith(ROOT_NAME + "/"):
                        raise SourceArchiveError("GCC Linaro tar archive contains an escaping link")
                if member.isfile():
                    unpacked_bytes += member.size
                    if unpacked_bytes > MAX_UNPACKED_BYTES:
                        raise SourceArchiveError("GCC Linaro tar archive exceeds its unpacked size limit")
                    if member.name in REQUIRED_GCC_SOURCE_FILES:
                        required_found.add(member.name)
            if members < len(REQUIRED_GCC_SOURCE_FILES) or required_found != REQUIRED_GCC_SOURCE_FILES:
                raise SourceArchiveError("GCC Linaro tar archive lacks canonical GCC 7 source files")
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
                content_type = response.headers.get_content_type().lower()
                if content_type in ("text/html", "application/xhtml+xml"):
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
    except HTTPError as exc:
        # urllib's exception string contains the URL, which may include a
        # short-lived signed query parameter. Report only the HTTP status.
        raise SourceArchiveError(
            f"Trusted HTTPS GCC Linaro source returned HTTP {exc.code}; "
            "verify that the publisher-backed mirror serves the pinned source archive"
        ) from None
    except (URLError, TimeoutError):
        # URLError.reason is arbitrary transport text and can embed secrets.
        raise SourceArchiveError(
            "Trusted HTTPS GCC Linaro source is unreachable or timed out; "
            "check the mirror and GitHub Actions runner network"
        ) from None
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def seed_local_archive(source: Path, expected_digest: str, destination: Path) -> str:
    """Install a manually recovered archive without requiring network access.

    A matching digest is required even for local files. Never mutate the
    original and never overwrite a valid cache until the copy validates.
    """
    expected_digest = validate_sha256(expected_digest)
    if source.name != ARCHIVE_NAME:
        raise SourceArchiveError(f"Local GCC Linaro source must be named {ARCHIVE_NAME}")
    if not source.is_file():
        raise SourceArchiveError("Configured local GCC Linaro archive is not a regular file")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise SourceArchiveError("Configured GCC Linaro archive is too large")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / ARCHIVE_NAME
    if target.exists():
        try:
            validate_archive(target, expected_digest)
        except SourceArchiveError:
            pass
        else:
            return "verified cached source"

    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination, prefix=".mod-linaro-", delete=False) as temp:
            staged = Path(temp.name)
            with source.open("rb") as incoming:
                shutil.copyfileobj(incoming, temp, length=1024 * 1024)
        validate_archive(staged, expected_digest)
        os.replace(staged, target)
        return "verified local source"
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=os.environ.get("MOD_LINARO_SOURCE_URL", ""))
    parser.add_argument("--source-file", type=Path, help="locally obtained GCC source .tar.xz (no network fetch)")
    parser.add_argument("--sha256", default=os.environ.get("MOD_LINARO_SOURCE_SHA256", ""))
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / "mod-workdir" / "download")
    args = parser.parse_args()
    try:
        if args.source_file is not None and args.source_url:
            raise SourceArchiveError("Choose either --source-file or --source-url, not both")
        if args.source_file is not None:
            if not args.sha256:
                raise SourceArchiveError(
                    "--source-file requires a verified --sha256 digest (64 hexadecimal characters); "
                    f"use --source-file /path/to/{ARCHIVE_NAME} --sha256 <trusted-sha256>"
                )
            result = seed_local_archive(args.source_file, args.sha256, args.cache_dir)
            print(f"MOD GCC Linaro 7.5 source: {result}")
            return 0
        if not args.source_url or not args.sha256:
            raise SourceArchiveError(
                "The old Linaro GCC 7.5 source URL now redirects to an HTML page. "
                f"Configure repository variable MOD_LINARO_SOURCE_URL (trusted HTTPS URL ending in {ARCHIVE_NAME}) "
                "and MOD_LINARO_SOURCE_SHA256 (independently verified 64-hex SHA-256 digest), "
                f"or pass --source-file /path/to/{ARCHIVE_NAME} --sha256 <trusted-sha256>. "
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
