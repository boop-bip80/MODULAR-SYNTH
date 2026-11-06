#!/usr/bin/env bash
# Source-only pre-upload gate for Windows artifacts on main and release tags.
# An artifact slug is SHA8 on ordinary main pushes or a tag on releases.
# This does not certify an installed plugin.
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 REPOSITORY win32|win64 RELEASE_SLUG" >&2
  exit 2
fi

repository="$1"
target="$2"
release_slug="$3"

case "$target" in
  win32|win64) ;;
  *) echo "invalid Windows target: $target" >&2; exit 2 ;;
esac
for value in "$repository" "$release_slug"; do
  if [[ ! "$value" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "invalid release artifact naming component" >&2
    exit 2
  fi
done

archive="${repository}-${target}-${release_slug}.zip"
if [[ ! -s "$archive" ]]; then
  echo "missing or empty Windows release ZIP: $archive" >&2
  exit 1
fi

shopt -s nullglob
installers=("Cardinal-${target}-"*-installer.exe)
if [[ "${#installers[@]}" -ne 1 ]]; then
  echo "expected exactly one Cardinal-${target} installer; found ${#installers[@]}" >&2
  exit 1
fi
if [[ ! -s "${installers[0]}" ]]; then
  echo "empty Windows release installer: ${installers[0]}" >&2
  exit 1
fi

# Require structurally intact release bundles, real Windows PE files of the
# requested architecture, and the exact plugin variants promised by packaging.
# Keeping this after the basename checks preserves the existing CLI contract.
python3 -B "$(dirname "$0")/verify-windows-payload.py" \
  --zip "$archive" --installer "${installers[0]}" --target "$target"
