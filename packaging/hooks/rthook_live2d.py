"""PyInstaller runtime hook: point live2d.v3.init at FrameworkShaders.

On macOS .app bundles, the `_v3cpp.so` may land under Contents/Frameworks while
package data (FrameworkShaders) lands under Contents/Resources. live2d.v3.init()
uses ``__file__`` as the shader root, which can miss the shaders. Patch init to
prefer any on-disk directory that actually contains FrameworkShaders.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _shader_candidates() -> list[Path]:
    bases: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        mp = Path(meipass)
        bases.append(mp / "live2d" / "v3")
        parent = mp.parent
        bases.append(parent / "Frameworks" / "live2d" / "v3")
        bases.append(parent / "Resources" / "live2d" / "v3")
        # Resources/live2d may be a symlink to Frameworks/live2d
        bases.append((parent / "Resources" / "live2d" / "v3").resolve())
        bases.append((parent / "Frameworks" / "live2d" / "v3").resolve())
    # Executable-adjacent (Contents/MacOS -> Contents)
    try:
        exe = Path(sys.executable).resolve()
        contents = exe.parent.parent
        bases.append(contents / "Frameworks" / "live2d" / "v3")
        bases.append(contents / "Resources" / "live2d" / "v3")
    except Exception:
        pass
    # De-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for b in bases:
        key = str(b)
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return out


def _patch_live2d_init() -> None:
    try:
        import live2d.v3 as v3
    except Exception:
        return

    if not hasattr(v3, "init_internal"):
        return

    original = v3.init

    def init() -> None:  # noqa: A001 — match upstream API
        for base in _shader_candidates():
            if (base / "FrameworkShaders").is_dir():
                v3.init_internal(str(base))
                return
        # Fall back to upstream behaviour (__file__ directory)
        return original()

    v3.init = init


_patch_live2d_init()
