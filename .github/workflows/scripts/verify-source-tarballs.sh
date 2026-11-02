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

    # A readable tar stream can still be stale, mis-rooted or missing modules.
    # Reject incomplete first-party source and panels before upload.
    # The versioned root follows Makefile's existing tar --transform rules.
    if ! tar --lzma -tf "$archive" | awk -v root="cardinal-${version}" '
        BEGIN {
            required["LICENSE"] = 1
            required["README.md"] = 1
            required["Makefile"] = 1
            required["plugins/ModularSynth/plugin.json"] = 1
            required["plugins/ModularSynth/src/plugin.hpp"] = 1
            # Keep all eight first-party C++ wrappers, DSP headers and panels
            # together; the source-level Python test compares this list with
            # the registered slugs in plugin.json to catch future drift.
            module_count = split("ChanceHold ClockedLFO FoldDrive FMVoice Macro8 MorphVCO StateFilter StereoEcho", slugs, " ")
            for (i = 1; i <= module_count; ++i) {
                required["plugins/ModularSynth/src/" slugs[i] ".cpp"] = 1
                required["plugins/ModularSynth/src/" slugs[i] ".hpp"] = 1
                required["plugins/ModularSynth/res/" slugs[i] ".svg"] = 1
            }
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
