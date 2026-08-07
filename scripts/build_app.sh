#!/usr/bin/env bash
# Build DexPet.app with PyInstaller (USTC mirror by default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

INDEX_URL="${PIP_INDEX_URL:-https://pypi.mirrors.ustc.edu.cn/simple/}"
TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.mirrors.ustc.edu.cn}"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pip install -U pyinstaller \
  -i "$INDEX_URL" \
  --trusted-host "$TRUSTED_HOST"

rm -rf build dist/DexPet dist/DexPet.app

pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/DexPet.spec

APP="$ROOT/dist/DexPet.app"
xattr -cr "$APP"
codesign --force --deep --sign - "$APP" >/dev/null

echo ""
echo "Built: $APP"
echo "Open with: open \"$APP\""
