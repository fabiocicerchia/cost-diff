#!/usr/bin/env bash
set -euo pipefail
# One-line installer for cost-diff
# Usage: curl -fsSL https://raw.githubusercontent.com/fabiocicerchia/cost-diff/main/install.sh | bash

if command -v pipx &>/dev/null; then
  pipx install git+https://github.com/fabiocicerchia/cost-diff
else
  pip install --user git+https://github.com/fabiocicerchia/cost-diff
fi
echo "cost-diff installed. Run: cost-diff --help"
