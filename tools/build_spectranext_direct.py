#!/usr/bin/env python3
"""Package a direct HTTPS launch using the canonical SpectraNext tools."""

import shutil
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_spectranext_direct.py SPXN_DIR")
    driver = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(driver.parent / "tools"))
    from build_installer import build_compact_tape_launcher
    from package_resource import stage
    from build_direct_tap import build as build_direct_tap

    root = Path(__file__).resolve().parents[1]
    build = root / "build"
    build.mkdir(exist_ok=True)
    (build / "SpecTalkZX-direct.tap").write_bytes(build_direct_tap(
        (build / "SpecTalkZX.tap").read_bytes(),
        (root / "packaging/spectranext/loading.scr").read_bytes(),
    ))
    (build / "spectranext-boot.zx").write_bytes(
        build_compact_tape_launcher("SPECTALK.TAP", "SPCTX")
    )
    output = build / "spectranext-direct"
    if output.exists():
        shutil.rmtree(output)
    files = stage(root / "packaging/spectranext/direct.json", output)
    print(f"Direct HTTPS resource: {output} ({len(files)} files)")


if __name__ == "__main__":
    main()
