#!/usr/bin/env bash
# Idempotent Cloud Agent install script for the MiniShop pilot study.
# Prepares a Python virtualenv, installs dependencies, and installs the
# Playwright Chromium browser used by the C1/C2 interface conditions.
set -euo pipefail

APP_DIR="dualsurface/minishop"

# System package required to create Python 3.12 virtualenvs on Ubuntu.
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends python3.12-venv

cd "${APP_DIR}"

# Create the virtualenv if it does not already exist (safe to re-run).
if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

# Playwright browser + its OS-level dependencies (needed for C1/C2 only).
sudo "$(command -v playwright)" install-deps chromium
playwright install chromium
