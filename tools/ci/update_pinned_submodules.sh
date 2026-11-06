#!/usr/bin/env bash
# Complete the recursive checkout outside actions/checkout's non-retrying stage.
# Gitlinks, not branch tips, determine each dependency's exact revision.
set -euo pipefail

source_url='https://gitlab.xiph.org/xiph/speexdsp.git'
mirror_url='https://github.com/xiph/speexdsp.git'
mirror_rule="url.${mirror_url}.insteadOf=${source_url}"

# The nested Rack manifest adds a trailing slash to its SpeexDSP URL on some
# Git versions; both spelling variants must resolve to the official mirror.
for suffix in '' '/'; do
    resolved="$(git -c "$mirror_rule" ls-remote --get-url "${source_url}${suffix}")"
    if [[ "$resolved" != "${mirror_url}${suffix}" ]]; then
        echo "Unexpected SpeexDSP checkout URL: $resolved" >&2
        exit 1
    fi
done

for attempt in 1 2 3; do
    if git -c "$mirror_rule" submodule update --init --recursive; then
        # Run before per-job dependency setup, including bare Ubuntu release
        # containers that have no Python installed yet. Git's status leading
        # character is a space only for an exact, initialized pinned Gitlink.
        statuses="$(git submodule status --recursive)"
        if [[ -z "$statuses" || "$statuses" != *'src/Rack/dep/speexdsp '* ]]; then
            echo 'Pinned nested Rack/SpeexDSP checkout was not populated.' >&2
            exit 1
        fi
        while IFS= read -r entry; do
            if [[ ! "$entry" =~ ^\ [[:xdigit:]]{40}[[:space:]] ]]; then
                echo "Uninitialized or non-pinned submodule: $entry" >&2
                exit 1
            fi
        done <<< "$statuses"
        exit 0
    fi
    if [[ "$attempt" -eq 3 ]]; then
        echo 'Pinned recursive submodule checkout failed after three attempts.' >&2
        exit 1
    fi
    echo "Transient pinned submodule checkout failure; retry $((attempt + 1))/3." >&2
    sleep "$((attempt * 5))"
done
