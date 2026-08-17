#!/usr/bin/env bash
# Fetch the pinned pandoc into vendor/. Every number in this repo is measured
# against this exact build; bump PANDOC_VERSION and re-run to move the baseline.
set -euo pipefail

PANDOC_VERSION="${PANDOC_VERSION:-3.10.2}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/vendor"
TARBALL="pandoc-${PANDOC_VERSION}-linux-amd64.tar.gz"
URL="https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/${TARBALL}"

if [ -x "${DEST}/pandoc/bin/pandoc" ] \
   && "${DEST}/pandoc/bin/pandoc" --version | head -1 | grep -q "${PANDOC_VERSION}"; then
  echo "pandoc ${PANDOC_VERSION} already present"
  exit 0
fi

mkdir -p "${DEST}"
echo "fetching ${URL}"
curl -fsSL "${URL}" -o "${DEST}/${TARBALL}"
tar xzf "${DEST}/${TARBALL}" -C "${DEST}"
rm -rf "${DEST}/pandoc"
mv "${DEST}/pandoc-${PANDOC_VERSION}" "${DEST}/pandoc"
rm -f "${DEST}/${TARBALL}"
"${DEST}/pandoc/bin/pandoc" --version | head -1
