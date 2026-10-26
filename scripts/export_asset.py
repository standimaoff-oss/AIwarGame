"""Export assets from a .blend with preflight checks. Run inside Blender.

blender --background FILE.blend --python export_asset.py -- \
    --output assets/<slug>/exports/<slug>.glb --format glb \
    [--collections House] [--objects SM_House_Door] [--apply-modifiers] \
    [--scale 1.0] [--animations] [--embed-textures] [--log export-log.json]

The blend file is NOT saved: selection is restored after the export and
modifiers are applied only in the exported copy. A JSON log records the
preflight findings, the exporter options actually accepted by this Blender
version and the resulting file size.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

import bpy

TOOL_VERSION = "1.0.0"
FORMATS = ("glb", "gltf", "fbx", "obj", "usd", "stl")
MESH_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}


def cli_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Export selected collections or objects.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", choices=FORMATS, required=True)
    parser.add_argument("--collections", default="")
    parser.add_argument("--objects", default="")
    parser.add_argument("--apply-modifiers", action="store_true", default=True)
    parser.add_argument("--keep-modifiers", dest="apply_modifiers", action="store_false")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--animations", action="store_true")
    parser.add_argument("--skins", action="store_true", default=True)
    parser.add_argument("--no-skins", dest="skins", action="store_false")
    parser.add_argument("--embed-textures", action="store_true")
    parser.add_argument("--draco", action="store_true")
    parser.add_argument("--draco-level", type=int, default=6)
    parser.add_argument("--triangulate", action="store_true")
    parser.add_argument("--yup", action="store_true", default=True)
    parser.add_argument("--no-yup", dest="yup", action="store_false")
    parser.add_argument("--axis-forward", default="-Z")
    parser.add_argument("--axis-up", default="Y")
    parser.add_argument("--log", default="")
    parser.add_argument("--fail-on-warning", action="store_true")
    parser.add_argument("--max-triangles", type=int, default=0)
    return parser.parse_args(argv)


def scope_objects(args):
    scene = bpy.context.scene
    selected = []
    seen = set()

    def add(obj):
        if obj.name in seen:
            return
        seen.add(obj.name)
        selected.append(obj)
        for child in obj.children:
            add(child)

    for name in [n.strip() for n in args.objects.split(",") if n.strip()]:
        obj = bpy.data.objects.get(name)
        if obj is None:
            print("warn: object not found: %s" % name, file=sys.stderr)
            continue
        add(obj)
    for name in [c.strip() for c in args.collections.split(",") if c.strip()]:
        collection = bpy.data.collections.get(name)
        if collection is None:
            print("warn: collection not found: %s" % name, file=sys.stderr)
            continue
        stack = [collection]
        while stack:
            current = stack.pop()
            stack.extend(current.children)
            for obj in current.all_objects:
                add(obj)
    if not selected:
        for obj in scene.objects:
            if obj.type in MESH_TYPES and obj.visible_get():
                add(obj)
        print("info: no --collections/--objects given, exporting visible geometry")
    return selected


def preflight(objects, args):
    findings = {"errors": [], "warnings": [], "info": []}
    triangles = 0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    has_armature = False
    for obj in objects:
        label = obj.name
        scale = tuple(round(abs(v), 6) for v in obj.scale)
        if any(v < 0 for v in obj.scale):
            findings["errors"].append("%s: negative scale %s (apply rotation/scale before export)" % (label, tuple(obj.scale)))
        if any(abs(v - 1.0) > 1e-4 for v in obj.scale):
            findings["warnings"].append("%s: unapplied scale %s" % (label, scale))
        if obj.parent is not None and any(abs(v - 1.0) > 1e-4 for v in obj.parent.scale):
            findings["warnings"].append("%s: parent %s has unapplied scale" % (label, obj.parent.name))
        if obj.type == "ARMATURE":
            has_armature = True
        if obj.type not in MESH_TYPES:
            findings["info"].append("%s: type %s is not exported as geometry" % (label, obj.type))
            continue
        obj_eval = obj.evaluated_get(depsgraph) if args.apply_modifiers else obj
        mesh = None
        try:
            mesh = obj_eval.to_mesh()
        except (RuntimeError, AttributeError):
            mesh = None
        if mesh is None:
            findings["info"].append("%s: no evaluated mesh" % label)
            continue
        try:
            triangles += sum(max(0, len(p.vertices) - 2) for p in mesh.polygons)
            if len(mesh.vertices) == 0:
                findings["warnings"].append("%s: empty mesh" % label)
            if not mesh.uv_layers:
                textured = False
                for slot in obj_eval.material_slots:
                    material = slot.material
                    if material and material.use_nodes:
                        textured = any(n.type == "TEX_IMAGE" for n in material.node_tree.nodes)
                if textured:
                    findings["warnings"].append("%s: no UV map while materials use image textures" % label)
            if not obj_eval.material_slots or all(s.material is None for s in obj_eval.material_slots):
                findings["info"].append("%s: no material assigned" % label)
        finally:
            try:
                obj_eval.to_mesh_clear()
            except (AttributeError, RuntimeError):
                pass
    findings["triangles"] = triangles
    if args.max_triangles and triangles > args.max_triangles:
        findings["warnings"].append("%d triangles exceed the agreed budget %d" % (triangles, args.max_triangles))
    if has_armature and not args.skins:
        findings["warnings"].append("armature present but --no-skins given")
    if has_armature and not args.animations:
        findings["info"].append("armature present; animations are not exported unless --animations is passed")
    if bpy.data.is_dirty:
        findings["info"].append("the file has unsaved changes; the export uses the in-memory state")
    return findings


def supported_kwargs(operator, kwargs):
    keys = set(operator.get_rna_type().properties.keys())
    accepted = {key: value for key, value in kwargs.items() if key in keys}
    dropped = sorted(set(kwargs) - set(accepted))
    return accepted, dropped


def build_kwargs(args, output):
    fmt = args.format
    if fmt in ("glb", "gltf"):
        kwargs = {
            "filepath": output,
            "export_format": "GLB" if fmt == "glb" else ("GLTF_EMBEDDED" if args.embed_textures else "GLTF_SEPARATE"),
            "use_selection": True,
            "use_visible": True,
            "export_yup": args.yup,
            "export_apply": args.apply_modifiers,
            "export_normals": True,
            "export_tangents": True,
            "export_materials": "EXPORT",
            "export_animations": args.animations,
            "export_skins": args.skins,
            "export_image_format": "AUTO",
            "export_lights": False,
            "export_cameras": False,
            "export_extras": True,
            "export_draco_mesh_compression_enable": args.draco,
            "export_draco_mesh_compression_level": args.draco_level,
            "export_triangulate_meshes": args.triangulate,
        }
        return bpy.ops.export_scene.gltf, kwargs
    if fmt == "fbx":
        kwargs = {
            "filepath": output,
            "use_selection": True,
            "global_scale": args.scale,
            "apply_scale_options": "FBX_SCALE_ALL",
            "apply_unit_scale": True,
            "axis_forward": args.axis_forward,
            "axis_up": args.axis_up,
            "use_mesh_modifiers": args.apply_modifiers,
            "mesh_smooth_type": "FACE" if args.triangulate else "OFF",
            "add_leaf_bones": False,
            "bake_anim": args.animations,
            "path_mode": "COPY" if args.embed_textures else "AUTO",
            "embed_textures": args.embed_textures,
        }
        return bpy.ops.export_scene.fbx, kwargs
    if fmt == "obj":
        kwargs = {
            "filepath": output,
            "export_selected_objects": True,
            "export_materials": True,
            "export_normals": True,
            "export_uv": True,
            "export_triangulated_mesh": args.triangulate,
            "forward_axis": "NEGATIVE_Z" if args.yup else "Y",
            "up_axis": "Y" if args.yup else "Z",
            "global_scale": args.scale,
            "path_mode": "COPY" if args.embed_textures else "AUTO",
        }
        if hasattr(bpy.ops.wm, "obj_export"):
            return bpy.ops.wm.obj_export, kwargs
        return bpy.ops.export_scene.obj, kwargs
    if fmt == "usd":
        kwargs = {
            "filepath": output,
            "selected_objects_only": True,
            "export_materials": True,
            "export_animation": args.animations,
            "apply_modifiers": args.apply_modifiers,
            "export_hair": False,
            "export_global_forward_selection": "Y" if args.yup else "Z",
            "export_global_up_selection": "Z" if args.yup else "Y",
        }
        return bpy.ops.wm.usd_export, kwargs
    kwargs = {
        "filepath": output,
        "export_selected_objects": True,
        "apply_modifiers": args.apply_modifiers,
        "export_normals": True,
        "export_uv": True,
        "export_triangulated_mesh": args.triangulate,
        "global_scale": args.scale,
        "ascii_format": False,
    }
    if hasattr(bpy.ops.wm, "stl_export"):
        return bpy.ops.wm.stl_export, kwargs
    return bpy.ops.export_mesh.stl, kwargs


def main():
    args = cli_args()
    output = os.path.abspath(args.output)
    folder = os.path.dirname(output)
    if folder:
        os.makedirs(folder, exist_ok=True)

    objects = scope_objects(args)
    if not objects:
        raise SystemExit("error: nothing selected for export")
    findings = preflight(objects, args)

    previous_active = bpy.context.view_layer.objects.active
    previous_selected = list(bpy.context.selected_objects)
    exported = False
    dropped = []
    used_kwargs = {}

    try:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            if obj.name in bpy.context.view_layer.objects:
                obj.select_set(True)
        first_mesh = next((obj for obj in objects if obj.type in MESH_TYPES), objects[0])
        bpy.context.view_layer.objects.active = first_mesh

        operator, kwargs = build_kwargs(args, output)
        used_kwargs, dropped = supported_kwargs(operator, kwargs)
        if dropped:
            findings["info"].append("options not supported by Blender %s and skipped: %s" % (
                bpy.app.version_string, ", ".join(dropped)))
        result = operator(**used_kwargs)
        exported = bool(result) and "FINISHED" in set(result)
    except (RuntimeError, AttributeError, TypeError) as exc:
        findings["errors"].append("export failed: %s" % exc)
    finally:
        try:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in previous_selected:
                if obj.name in bpy.context.view_layer.objects:
                    obj.select_set(True)
            bpy.context.view_layer.objects.active = previous_active
        except (RuntimeError, AttributeError):
            pass

    size = os.path.getsize(output) if os.path.isfile(output) else 0
    if size == 0:
        findings["errors"].append("export produced no file: %s" % output)
    siblings = []
    if folder and os.path.isdir(folder):
        siblings = [n for n in sorted(os.listdir(folder))
                    if n != os.path.basename(output) and not n.startswith(".")]

    log = {
        "tool": "export_asset.py",
        "version": TOOL_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source_file": bpy.data.filepath,
        "blender": bpy.app.version_string,
        "output": output.replace(os.sep, "/"),
        "format": args.format,
        "exported": bool(exported and size > 0),
        "size_bytes": size,
        "objects": [obj.name for obj in objects],
        "options": used_kwargs,
        "dropped_options": dropped,
        "sibling_files": siblings[:200],
        "triangles": findings.get("triangles", 0),
        "errors": findings["errors"],
        "warnings": findings["warnings"],
        "info": findings["info"],
        "note": "The blend file was not saved. Verify the export by importing it into a clean scene or the target engine.",
    }
    log_path = args.log or os.path.join(folder or ".", "%s-export-log.json" % os.path.splitext(os.path.basename(output))[0])
    with open(log_path, "w", encoding="utf-8") as handle:
        json.dump(log, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    for message in findings["errors"]:
        print("ERROR  %s" % message)
    for message in findings["warnings"]:
        print("WARN   %s" % message)
    print("export_asset %s: %s -> %s (%.2f MB, %d triangles)" % (
        TOOL_VERSION, args.format, output, size / 1048576.0, log["triangles"]))
    print("  log: %s" % log_path)
    if findings["errors"] or (args.fail_on_warning and findings["warnings"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
