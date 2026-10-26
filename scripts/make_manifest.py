"""Generate asset-manifest.json from a .blend. Run inside Blender, read-only.

blender --factory-startup --background FILE.blend --python make_manifest.py -- \
    --output assets/<slug>/manifest/asset-manifest.json --slug <slug> \
    --archetype architecture [--collections House] [--repo-root .] [--merge]

The file is never saved and no modifier is applied to the stored data: geometry
is read from the evaluated depsgraph. Manual blocks of an existing manifest
(proofs, provenance, open_items, exports, audit, identity fields, budget
limits) are preserved unless --no-merge is passed.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import sys

import bpy
from mathutils import Vector

TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = 2
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
COLORSPACE_MAP = {"sRGB": "sRGB", "Non-Color": "Non-Color", "Raw": "Raw"}
MAP_TOKENS = {
    "basecolor": "BaseColor", "albedo": "BaseColor", "diffuse": "BaseColor",
    "roughness": "Roughness", "metallic": "Metallic", "metalness": "Metallic",
    "normaldx": "NormalDX", "normal": "Normal", "height": "Height",
    "displacement": "Height", "ao": "AO", "occlusion": "AO", "orm": "ORM",
    "emissive": "Emissive", "emission": "Emissive", "opacity": "Opacity",
    "alpha": "Opacity", "mask": "Opacity", "curvature": "Curvature",
    "thickness": "Thickness", "sheen": "Sheen", "anisotropy": "Anisotropy",
}


def cli_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Write an asset manifest from the open blend file.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--slug")
    parser.add_argument("--name")
    parser.add_argument("--archetype", default="other")
    parser.add_argument("--variant", default="")
    parser.add_argument("--status", default="wip", choices=["wip", "review", "done", "blocked"])
    parser.add_argument("--version", dest="asset_version", default="")
    parser.add_argument("--task-issue")
    parser.add_argument("--branch", default="")
    parser.add_argument("--source-file", default="", help="repository-relative path of the .blend")
    parser.add_argument("--collections", default="", help="comma separated collection names (default: all)")
    parser.add_argument("--objects", default="", help="comma separated object names (default: all)")
    parser.add_argument("--frame", type=int, help="frame to measure (default: current)")
    parser.add_argument("--repo-root", default="", help="used to make texture paths repository-relative")
    parser.add_argument("--blend-path", default="", help="repository-relative source_file override")
    parser.add_argument("--no-merge", action="store_true", help="do not preserve manual blocks of an existing manifest")
    parser.add_argument("--deep", action="store_true", help="count triangles per collection (slower)")
    return parser.parse_args(argv)


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def mm_factor(scene):
    scale = float(scene.unit_settings.scale_length or 1.0)
    if not finite(scale) or scale <= 0:
        scale = 1.0
    return scale * 1000.0


def clean(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 4)
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def resolve_collection(name):
    collection = bpy.data.collections.get(name)
    return collection


def collect_objects(scene, args):
    wanted_collections = [c.strip() for c in args.collections.split(",") if c.strip()]
    wanted_objects = [o.strip() for o in args.objects.split(",") if o.strip()]
    objects = []
    seen = set()
    if wanted_objects:
        for name in wanted_objects:
            obj = bpy.data.objects.get(name)
            if obj is None:
                print("warn: object not found: %s" % name, file=sys.stderr)
                continue
            if obj.name not in seen:
                seen.add(obj.name)
                objects.append(obj)
    if wanted_collections:
        for name in wanted_collections:
            collection = resolve_collection(name)
            if collection is None:
                print("warn: collection not found: %s" % name, file=sys.stderr)
                continue
            stack = [collection]
            while stack:
                current = stack.pop()
                stack.extend(current.children)
                for obj in current.all_objects if hasattr(current, "all_objects") else current.objects:
                    if obj.name not in seen:
                        seen.add(obj.name)
                        objects.append(obj)
    if not objects:
        objects = [obj for obj in scene.objects if obj.name not in seen] or list(scene.objects)
    return objects


def world_bbox(obj_eval, matrix_world):
    points = []
    mesh = None
    try:
        mesh = obj_eval.to_mesh()
    except (RuntimeError, AttributeError):
        mesh = None
    if mesh is not None:
        try:
            for vertex in mesh.vertices:
                points.append(matrix_world @ vertex.co)
        finally:
            obj_eval.to_mesh_clear()
    else:
        for corner in obj_eval.bound_box:
            points.append(matrix_world @ Vector(corner))
    if not points:
        return None
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    return [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]


def mesh_counts(obj_eval):
    triangles = 0
    vertices = 0
    mesh = None
    try:
        mesh = obj_eval.to_mesh()
    except (RuntimeError, AttributeError):
        mesh = None
    if mesh is None:
        return 0, 0
    try:
        vertices = len(mesh.vertices)
        for polygon in mesh.polygons:
            count = len(polygon.vertices)
            triangles += max(0, count - 2)
    finally:
        obj_eval.to_mesh_clear()
    return triangles, vertices


def guess_map(name):
    tokens = [t for t in name.replace("-", "_").replace(".", "_").split("_") if t]
    for token in reversed(tokens):
        key = token.lower()
        if key in MAP_TOKENS:
            return MAP_TOKENS[key]
    return "Other"


def image_entry(image, repo_root, blend_dir):
    path = bpy.path.abspath(image.filepath) if image.filepath else ""
    packed = bool(image.packed_file)
    relative = path
    if repo_root:
        try:
            candidate = os.path.relpath(path, repo_root)
            if not candidate.startswith(".."):
                relative = candidate.replace(os.sep, "/")
        except ValueError:
            pass
    elif blend_dir:
        try:
            candidate = os.path.relpath(path, blend_dir)
            if not candidate.startswith(".."):
                relative = candidate.replace(os.sep, "/")
        except ValueError:
            pass
    width, height = (int(image.size[0]), int(image.size[1])) if len(image.size) >= 2 else (0, 0)
    colorspace = getattr(image.colorspace_settings, "name", "")
    return {
        "path": relative or image.name,
        "map": guess_map(image.name if not path else os.path.basename(path)),
        "set": "",
        "width": width,
        "height": height,
        "colorspace": COLORSPACE_MAP.get(colorspace, "Unknown"),
        "packed": packed,
        "tilable": None,
        "provenance": "",
    }


def material_images(material):
    images = []
    if not material or not material.use_nodes or not material.node_tree:
        return images
    for node in material.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not None:
            images.append(node.image)
    return images


def build(args):
    scene = bpy.context.scene
    mm = mm_factor(scene)
    if args.frame is not None:
        scene.frame_set(args.frame)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()

    objects = collect_objects(scene, args)
    blend_dir = os.path.dirname(bpy.path.abspath(bpy.data.filepath)) if bpy.data.filepath else ""
    repo_root = os.path.abspath(args.repo_root) if args.repo_root else ""

    bbox_min = [math.inf, math.inf, math.inf]
    bbox_max = [-math.inf, -math.inf, -math.inf]
    triangles = vertices = mesh_objects = 0
    materials_used = {}
    images_used = {}

    for obj in objects:
        obj_eval = obj.evaluated_get(depsgraph)
        matrix_world = obj_eval.matrix_world
        if obj_eval.type in GEOMETRY_TYPES:
            box = world_bbox(obj_eval, matrix_world)
            if box:
                for index in range(3):
                    bbox_min[index] = min(bbox_min[index], box[index])
                    bbox_max[index] = max(bbox_max[index], box[index + 3])
        if obj_eval.type == "MESH":
            mesh_objects += 1
            tri, verts = mesh_counts(obj_eval)
            triangles += tri
            vertices += verts
            for slot in obj_eval.material_slots:
                material = slot.material
                if material is None:
                    continue
                materials_used.setdefault(material.name, {"slots": 0, "procedural": material.use_nodes,
                                                          "images": [], "packed": False})
                materials_used[material.name]["slots"] += 1
                for image in material_images(material):
                    materials_used[material.name]["images"].append(image.name)
                    images_used.setdefault(image.name, image)

    bbox = [0.0, 0.0, 0.0]
    if all(finite(v) for v in bbox_min) and all(finite(v) for v in bbox_max):
        bbox = [(bbox_max[i] - bbox_min[i]) * mm for i in range(3)]

    collections = []
    for collection in bpy.data.collections:
        entry = {
            "name": collection.name,
            "objects": len(collection.objects),
            "children": [child.name for child in collection.children],
        }
        if args.deep:
            total = 0
            for obj in collection.all_objects:
                if obj.type == "MESH":
                    obj_eval = obj.evaluated_get(depsgraph)
                    total += mesh_counts(obj_eval)[0]
            entry["triangles"] = total
        movable = any(obj.parent is not None and obj.parent.type == "ARMATURE"
                      or (obj.animation_data and obj.animation_data.action) for obj in collection.objects)
        if movable:
            entry["movable"] = True
        collections.append(entry)

    materials = []
    for name, info in sorted(materials_used.items()):
        materials.append({
            "name": name,
            "slots": info["slots"],
            "procedural": bool(info["procedural"]) and not info["images"],
            "images": sorted(set(info["images"])),
            "packed": any(images_used[i].packed_file for i in set(info["images"]) if i in images_used),
        })

    textures = []
    for name, image in sorted(images_used.items()):
        entry = image_entry(image, repo_root, blend_dir)
        entry["provenance"] = ""
        entry["tilable"] = False
        textures.append(entry)

    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    shape_keys = []
    for obj in objects:
        data = getattr(obj, "data", None)
        keys = getattr(data, "shape_keys", None) if data is not None else None
        if keys is not None:
            for key in keys.key_blocks:
                if key.name != "Basis":
                    shape_keys.append("%s:%s" % (obj.name, key.name))
    drivers = 0
    for obj in objects:
        animation = getattr(obj, "animation_data", None)
        if animation is not None and animation.drivers:
            drivers += len(animation.drivers)
    rig_type = "none"
    if armatures:
        rig_type = "armature"
    elif drivers:
        rig_type = "drivers"
    elif any(obj.parent is not None for obj in objects):
        rig_type = "pivots"
    actions = [action.name for action in bpy.data.actions]
    animation_kind = "staged" if actions else "none"

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "make_manifest.py %s (Blender %s)" % (TOOL_VERSION, bpy.app.version_string),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source_file": args.source_file or args.blend_path or bpy.data.filepath,
        "identity": {
            "slug": args.slug or (os.path.splitext(os.path.basename(bpy.data.filepath))[0] if bpy.data.filepath else ""),
            "name": args.name or "",
            "archetype": args.archetype,
            "variant": args.variant,
            "version": args.asset_version,
            "status": args.status,
            "task_issue": args.task_issue,
            "branch": args.branch,
        },
        "units": {
            "unit": (scene.unit_settings.length_unit or "").lower()[:2] or "m",
            "scale_length": float(scene.unit_settings.scale_length or 1.0),
            "up_axis": "Z",
            "export_up_axis": "Y",
            "unit_system": scene.unit_settings.system or "METRIC",
        },
        "dimensions_mm": {
            "bbox": clean(bbox),
            "frame": int(scene.frame_current),
            "includes": "",
            "scope": ("collections: " + args.collections) if args.collections
                     else ("objects: " + args.objects) if args.objects else "all scene objects",
        },
        "budget": {
            "triangles": int(triangles),
            "vertices": int(vertices),
            "objects": int(len(objects)),
            "material_sets": int(len(materials)),
            "texture_resolution": "",
            "lods": 0,
            "udim_tiles": 0,
        },
        "collections": collections,
        "materials": materials,
        "textures": textures,
        "rig": {
            "type": rig_type,
            "armatures": [obj.name for obj in armatures],
            "bones": sum(len(obj.data.bones) for obj in armatures),
            "controls": [],
            "shape_keys": shape_keys[:200],
            "frame_start": int(scene.frame_start),
            "frame_end": int(scene.frame_end),
            "animation_kind": animation_kind,
            "notes": "mesh objects: %d; drivers: %d; actions: %s" % (mesh_objects, drivers, ", ".join(actions[:5])),
        },
        "exports": [],
        "proofs": [],
        "audit": {"config": "", "report": "", "status": "not_run", "checks_total": 0, "checks_failed": 0},
        "provenance": [],
        "open_items": [],
    }
    return manifest


MANUAL_BLOCKS = ("proofs", "provenance", "open_items", "exports", "audit")
MANUAL_IDENTITY = ("name", "variant", "status", "task_issue", "branch", "slug")


def merge(existing, generated):
    for block in MANUAL_BLOCKS:
        if existing.get(block):
            generated[block] = existing[block]
    identity = existing.get("identity") or {}
    for key in MANUAL_IDENTITY:
        if identity.get(key) and not generated["identity"].get(key):
            generated["identity"][key] = identity[key]
    budget = existing.get("budget") or {}
    for key in ("triangles_limit", "texture_resolution", "lods", "udim_tiles"):
        if budget.get(key):
            generated["budget"][key] = budget[key]
    units = existing.get("units") or {}
    for key in ("up_axis", "export_up_axis", "unit"):
        if units.get(key):
            generated["units"][key] = units[key]
    dims = existing.get("dimensions_mm") or {}
    if dims.get("includes"):
        generated["dimensions_mm"]["includes"] = dims["includes"]
    roles = {item["name"]: item for item in (existing.get("collections") or []) if isinstance(item, dict)}
    for entry in generated["collections"]:
        old = roles.get(entry["name"])
        if old:
            for key in ("role", "movable", "pivot"):
                if key in old and key not in entry:
                    entry[key] = old[key]
    rig = existing.get("rig") or {}
    for key in ("controls", "notes", "type"):
        if rig.get(key) and key != "type":
            generated["rig"][key] = rig[key]
    for key in ("source_file",):
        if existing.get(key) and not generated.get(key):
            generated[key] = existing[key]
    texture_sets = {item.get("path"): item for item in (existing.get("textures") or []) if isinstance(item, dict)}
    for entry in generated["textures"]:
        old = texture_sets.get(entry["path"])
        if old:
            for key in ("set", "tilable", "provenance", "map"):
                if old.get(key) not in (None, ""):
                    entry[key] = old[key]
    return generated


def main():
    args = cli_args()
    if bpy.data.filepath:
        print("info: source blend = %s" % bpy.data.filepath)
    else:
        print("warn: the file has never been saved; source_file will be empty", file=sys.stderr)

    generated = build(args)

    existing = {}
    output_path = os.path.abspath(args.output)
    if not args.no_merge and os.path.isfile(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as handle:
                existing = json.load(handle)
        except (OSError, ValueError) as exc:
            print("warn: existing manifest not readable (%s); writing a fresh one" % exc, file=sys.stderr)
    if existing and existing.get("schema_version") == SCHEMA_VERSION:
        generated = merge(existing, generated)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(clean(generated), handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print("make_manifest %s: wrote %s" % (TOOL_VERSION, output_path))
    print("  bbox mm: %s | triangles: %d | objects: %d | materials: %d | textures: %d | rig: %s" % (
        generated["dimensions_mm"]["bbox"], generated["budget"]["triangles"],
        generated["budget"]["objects"], generated["budget"]["material_sets"],
        len(generated["textures"]), generated["rig"]["type"]))
    print("  the blend file was NOT saved")


if __name__ == "__main__":
    main()
