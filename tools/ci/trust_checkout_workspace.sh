#!/usr/bin/env bash
# actions/checkout@v4 adds safe.directory under a temporary HOME which is
# restored before subsequent container run: steps. Git may then reject a
# checkout mounted from the host runner as having dubious ownership.
# Trust only the runner-declared checkout directory, never '*' or its parent.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != 'true' ]]; then
    exit 0
fi

if [[ -z "${GITHUB_WORKSPACE:-}" || "${GITHUB_WORKSPACE}" != /* || ! -d "${GITHUB_WORKSPACE}" ]]; then
    echo 'Cannot establish a valid absolute GITHUB_WORKSPACE for Git checkout trust.' >&2
    exit 1
fi

workspace="$(cd -- "$GITHUB_WORKSPACE" && pwd -P)"
current="$(pwd -P)"
if [[ "$workspace" != "$current" || ! -e "$current/.git" ]]; then
    echo 'Refusing to trust a checkout outside the exact GITHUB_WORKSPACE repository.' >&2
    exit 1
fi

# Deliberately use the job's real HOME, not actions/checkout's temporary HOME.
# Only the one exact workspace can pass Git's ownership safety check.
git config --global --add safe.directory "$workspace"
