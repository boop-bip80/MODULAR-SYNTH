#!/usr/bin/env bash
# Validate both source archives before a fork-owned release can publish them.
# GNU tar --lzma matches the existing Makefile recipe despite the .tar.xz names.
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[0-9][0-9A-Za-z._+-]*$ ]]; then
    echo "Usage: $0 <safe-Makefile-version>" >&2
    exit 2
fi

version="$1"
# Keep source-release module inventory in sync with the actual manifest.
# Reject malformed or duplicate entries before passing names to awk.
if ! module_slugs="$(python3 -B - <<'PY'
import json
import re
from pathlib import Path

path = Path("plugins/ModularSynth/plugin.json")
manifest = json.loads(path.read_text(encoding="utf-8"))
assert isinstance(manifest, dict) and manifest.get("slug") == "ModularSynth", "wrong plugin"
entries = manifest.get("modules")
assert isinstance(entries, list) and entries, "empty or malformed module list"
slugs = [entry.get("slug") if isinstance(entry, dict) else None for entry in entries]
assert all(isinstance(s, str) and re.fullmatch(r"[A-Z][A-Za-z0-9]{1,39}", s) for s in slugs), "invalid module slug"
assert len({s.casefold() for s in slugs}) == len(slugs), "duplicate module slug"
assert {"ChanceHold", "ClockedLFO", "FoldDrive", "FMVoice", "Macro8", "MorphVCO", "StateFilter", "StereoEcho"}.issubset(slugs), "lost original modules"
print(" ".join(sorted(slugs)))
PY
)"; then
    echo "Invalid or missing first-party source manifest" >&2
    exit 1
fi

for archive in "../cardinal-${version}.tar.xz" "../cardinal+deps-${version}.tar.xz"; do
    if [[ ! -s "$archive" ]]; then
        echo "Missing or empty source release archive: $archive" >&2
        exit 1
    fi

    # A readable tar stream can still be stale, mis-rooted or missing modules.
    # Reject incomplete first-party source and panels before upload.
    # The versioned root follows Makefile's existing tar --transform rules.
    if ! tar --lzma -tf "$archive" | awk -v root="cardinal-${version}" -v module_names="$module_slugs" '
        BEGIN {
            required["LICENSE"] = 1
            required["README.md"] = 1
            required["Makefile"] = 1
            required["plugins/ModularSynth/plugin.json"] = 1
            required["plugins/ModularSynth/src/plugin.hpp"] = 1
            # Every declared first-party module travels with its wrapper,
            # DSP header, and panel. Do not maintain a second hardcoded list.
            module_count = split(module_names, slugs, " ")
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
    # A same-named but stale manifest can otherwise masquerade as current.
    if ! cmp -s "plugins/ModularSynth/plugin.json" <(tar --lzma -xOf "$archive" "cardinal-${version}/plugins/ModularSynth/plugin.json" 2>/dev/null); then
        echo "Source archive manifest differs from current checkout: $archive" >&2
        exit 1
    fi
done
