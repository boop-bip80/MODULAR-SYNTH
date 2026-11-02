#!/usr/bin/env bash
# Validate both source archives before a fork-owned release can publish them.
# GNU tar --lzma matches the existing Makefile recipe despite the .tar.xz names.
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

    # A readable tar stream alone can be stale, mis-rooted or missing this
    # fork's own module. Reject these cases before upload. The parent-root
    # prefix follows Makefile's existing tar --transform rules.
    if ! tar --lzma -tf "$archive" | awk -v root="cardinal-${version}" '
        BEGIN {
            required["LICENSE"] = 1
            required["README.md"] = 1
            required["Makefile"] = 1
            required["plugins/ModularSynth/plugin.json"] = 1
            required["plugins/ModularSynth/src/MorphVCO.cpp"] = 1
        }
        {
            entry = $0
            if (entry == root || entry == root "/")
                next
            if (index(entry, root "/") != 1) {
                print "Archive member escapes versioned root: " entry > "/dev/stderr"
                invalid = 1
                next
            }
            path = substr(entry, length(root) + 2)
            count = split(path, components, "/")
            for (i = 1; i <= count; ++i) {
                if (components[i] == "..") {
                    print "Archive member contains parent traversal: " entry > "/dev/stderr"
                    invalid = 1
                    next
                }
            }
            if (path in required)
                found[path] = 1
        }
        END {
            for (path in required) {
                if (!(path in found)) {
                    print "Source archive missing required member: " path > "/dev/stderr"
                    invalid = 1
                }
            }
            if (invalid)
                exit 1
        }
    '; then
        echo "Invalid or incomplete source release archive: $archive" >&2
        exit 1
    fi
done
