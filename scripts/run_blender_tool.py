#!/usr/bin/env python3
"""Run one of this repository's Blender-only scripts with the headless bpy module.

Example:
    python scripts/run_blender_tool.py --blend assets/ppsh-41/source/ppsh-41.blend \
        --script scripts/audit_blend.py --args "--config ... --output ..."

The wrapper opens the requested .blend first, then executes the target script with
the arguments that follow --args. It never saves the opened file.
"""

from __future__ import annotations

import argparse
import runpy
import shlex
import sys
from pathlib import Path

import bpy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--args", nargs=argparse.REMAINDER, default=[])
    opts = parser.parse_args()
    blend = str(Path(opts.blend).resolve())
    script = str(Path(opts.script).resolve())
    bpy.ops.wm.open_mainfile(filepath=blend)
    bpy.context.view_layer.update()
    extra = opts.args
    if extra and extra[0] == "--":
        extra = extra[1:]
    # Accept either separate argv items or one quoted argument string.
    if len(extra) == 1 and " " in extra[0]:
        extra = shlex.split(extra[0])
    sys.argv = [script, "--", *extra]
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
