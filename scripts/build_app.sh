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

# Live2D shaders are required at runtime when live2d-py is installed.
if ! python -c "import live2d.v3" >/dev/null 2>&1; then
  echo "warning: live2d.v3 not importable; .app will lack Live2D (sprite-only)." >&2
  echo "         install with: pip install -e '.[live2d]'" >&2
fi

rm -rf build dist/DexPet dist/DexPet.app

pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/DexPet.spec

APP="$ROOT/dist/DexPet.app"

# macOS BUNDLE often puts the .so under Frameworks and datas under Resources.
# Ensure FrameworkShaders sit next to _v3cpp.so (and under Resources) so
# live2d.v3.init / our rthook can find them.
_fix_live2d_shaders() {
  local site_v3 src dest
  site_v3="$(python -c 'import live2d.v3, pathlib; print(pathlib.Path(live2d.v3.__file__).parent)' 2>/dev/null || true)"
  if [[ -z "$site_v3" || ! -d "$site_v3/FrameworkShaders" ]]; then
    return 0
  fi
  src="$site_v3/FrameworkShaders"
  for dest in \
    "$APP/Contents/Frameworks/live2d/v3" \
    "$APP/Contents/Resources/live2d/v3"
  do
    mkdir -p "$dest"
    # If Resources/live2d is a symlink to Frameworks/live2d, one copy covers both.
    rm -rf "$dest/FrameworkShaders"
    cp -R "$src" "$dest/FrameworkShaders"
    echo "Synced FrameworkShaders -> $dest/FrameworkShaders"
  done
}

_fix_live2d_shaders

if [[ -d "$APP/Contents/Frameworks/live2d/v3" ]]; then
  if [[ ! -d "$APP/Contents/Frameworks/live2d/v3/FrameworkShaders" ]]; then
    echo "error: live2d bundled but FrameworkShaders missing" >&2
    exit 1
  fi
  echo "OK: FrameworkShaders present in app bundle"
fi

xattr -cr "$APP"
codesign --force --deep --sign - "$APP" >/dev/null

echo ""
echo "Built: $APP"
echo "Open with: open \"$APP\""
echo "If Gatekeeper blocks: xattr -cr \"$APP\"  (already done by this script)"
echo "Logs (frozen): ~/Library/Application Support/DexPet/logs/app.log"
