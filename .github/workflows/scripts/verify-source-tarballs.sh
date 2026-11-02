#!/usr/bin/env bash
# Confirm both archives produced by Makefile's source-tarball recipes are
# nonempty and readable before a GitHub Release can be published.
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[0-9][0-9A-Za-z._+-]*$ ]]; then
    echo "Usage: $0 <safe-Makefile-version>" >&2
    exit 2
fi

version="$1"
for archive in "../cardinal-${version}.tar.xz" "../cardinal+deps-${version}.tar.xz"; do
    if [[ ! -s "$archive" ]]; then
        echo "Missing or empty source release archive: $archive" >&2
        exit 1
    fi
    # Makefile uses GNU tar --lzma (not --xz) despite the inherited .tar.xz
    # filenames. Keep the decoder consistent with the existing recipe.
    if ! tar --lzma -tf "$archive" >/dev/null; then
        echo "Unreadable source release archive: $archive" >&2
        exit 1
    fi
done
