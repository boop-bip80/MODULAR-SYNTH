#!/bin/sh

# Download the exact Inno Setup version used by create-windows-installer.sh.
# This is deliberately independent of Wine so it can be tested on any CI host.
set -eu

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    echo "usage: $0 destination.exe" >&2
    exit 2
fi

destination=$1
url=https://github.com/jrsoftware/issrc/releases/download/is-6_0_5/innosetup-6.0.5.exe
# SHA-256 published in the official, immutable jrsoftware/issrc release asset.
sha256=ae6823b523df87e9441789e51845434e4e0e70aac0b88afe80f94f20f4b98acb

verify() {
    printf '%s  %s\n' "$sha256" "$1" | sha256sum --check --status
}

if [ -f "$destination" ]; then
    if verify "$destination"; then
        exit 0
    fi
    echo "Cached Inno Setup 6.0.5 has the wrong SHA-256; replacing it" >&2
fi

# Download to a sibling file and only replace the cache after checksum success.
tmp=$(mktemp "${destination}.tmp.XXXXXX")
trap 'rm -f -- "$tmp"' 0
trap 'exit 1' 1 2 15

if ! curl --fail --location --retry 5 --retry-delay 2 --output "$tmp" "$url"; then
    echo "Failed to download Inno Setup 6.0.5 from its official release" >&2
    exit 1
fi
if ! verify "$tmp"; then
    echo "Downloaded Inno Setup 6.0.5 failed SHA-256 verification" >&2
    exit 1
fi

mv -f -- "$tmp" "$destination"
trap - 0 1 2 15
