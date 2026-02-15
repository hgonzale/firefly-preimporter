#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAP_DIR="${HOME}/Library/Taps/honkeandpastrami/homebrew-firefly-preimporter"
FORMULA_DIR="${REPO_DIR}/homebrew/Formula"

# Register the tap by symlinking homebrew/ into Homebrew's taps (one-time)
if [[ ! -e "${TAP_DIR}" ]]; then
  mkdir -p "$(dirname "${TAP_DIR}")"
  ln -s "${REPO_DIR}/homebrew" "${TAP_DIR}"
  echo "Tap registered: ${TAP_DIR} -> ${REPO_DIR}/homebrew"
fi

# Fetch the latest formula asset from GitHub releases
mkdir -p "${FORMULA_DIR}"
curl -fsSL \
  "https://github.com/hgonzale/firefly-preimporter/releases/latest/download/firefly-preimporter.rb" \
  -o "${FORMULA_DIR}/firefly-preimporter.rb"

# Install or upgrade
if brew list honkeandpastrami/firefly-preimporter &>/dev/null; then
  brew upgrade honkeandpastrami/firefly-preimporter
else
  brew install honkeandpastrami/firefly-preimporter
fi
