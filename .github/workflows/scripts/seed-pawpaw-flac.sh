#!/usr/bin/env bash
set -euo pipefail

# PawPaw@dd0fd459 downloads FLAC 1.5.0 into $HOME/PawPawBuilds/downloads.
# Its download() helper trusts an existing file, so seed and verify that exact
# cache entry before bootstrap instead of using its unreliable TLS fallback.
readonly FLAC_VERSION="1.5.0"
readonly FLAC_ARCHIVE="flac-${FLAC_VERSION}.tar.xz"
readonly FLAC_SHA256="f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920"
readonly FLAC_URL="https://github.com/xiph/flac/releases/download/${FLAC_VERSION}/${FLAC_ARCHIVE}"
readonly PAWPAW_DOWNLOAD_DIR="${HOME}/PawPawBuilds/downloads"
readonly DESTINATION="${PAWPAW_DOWNLOAD_DIR}/${FLAC_ARCHIVE}"

check_sha256() {
  local computed
  if command -v sha256sum >/dev/null 2>&1; then
    computed="$(sha256sum "$1" | cut -d " " -f 1)"
  else
    computed="$(shasum -a 256 "$1" | cut -d " " -f 1)"
  fi
  [[ "${computed}" == "${FLAC_SHA256}" ]]
}

mkdir -p "${PAWPAW_DOWNLOAD_DIR}"
if [[ -f "${DESTINATION}" ]] && check_sha256 "${DESTINATION}"; then
  echo "Verified cached ${FLAC_ARCHIVE}; skipping download"
  exit 0
fi

temp_file="$(mktemp "${PAWPAW_DOWNLOAD_DIR}/.flac-${FLAC_VERSION}.XXXXXXXX")"
trap 'rm -f "${temp_file}"' EXIT
echo "Fetching ${FLAC_ARCHIVE} from the official Xiph GitHub release"
curl_retry_flags=(--retry 5 --retry-delay 2)
# Older macOS system curl versions do not support --retry-all-errors.
if curl --help all 2>/dev/null | grep -F -- "--retry-all-errors" >/dev/null; then
  curl_retry_flags+=(--retry-all-errors)
fi
curl --fail --location --silent --show-error \
  "${curl_retry_flags[@]}" \
  "${FLAC_URL}" --output "${temp_file}"
if ! check_sha256 "${temp_file}"; then
  echo "SHA-256 mismatch for official FLAC release asset; refusing to cache" >&2
  exit 1
fi
mv -f "${temp_file}" "${DESTINATION}"
trap - EXIT
echo "Verified and cached ${FLAC_ARCHIVE}"
