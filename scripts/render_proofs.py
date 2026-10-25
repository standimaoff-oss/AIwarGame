"""Render the standard proof set from a .blend. Run inside Blender.

blender --background FILE.blend --python render_proofs.py -- \
    --output assets/<slug>/renders [--collections House] [--views front,iso] \
    [--turntable 24] [--clay] [--wireframe] [--resolution 1600] [--engine auto] \
    [--samples 128] [--hdri /path/studio.exr] [--frame 1]

The blend file is NEVER saved: cameras, lights, world and display settings are
created in memory, restored at the end and proofs-index.json is written next to
the images. Use it for silhouette, clay, macro, turntable and scale proofs.
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
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}

VIEWS = {
    "front": Vector((0.0, -1.0, 0.0)),
    "back": Vector((0.0, 1.0, 0.0)),
    "left": Vector((-1.0, 0.0, 0.0)),
    "right": Vector((1.0, 0.0, 0.0)),
    "top": Vector((0.0, 0.0, 1.0)),
    "bottom": Vector((0.0, 0.0, -1.0)),
    "iso": Vector((1.0, -1.0, 0.72)),
    "iso2": Vector((-1.0, -1.0, 0.72)),
    "hero": Vector((0.85, -1.0, 0.35)),
}
ORTHO_VIEWS = {"front", "back", "left", "right", "top", "bottom"}


def cli_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Render proof images without saving the blend file.")
    parser.add_argument("--output", required=True, help="folder for the rendered images")
    parser.add_argument("--collections", default="", help="comma separated collections to frame (default: visible scene)")
    parser.add_argument("--objects", default="", help="comma separated objects to frame")
    parser.add_argument("--views", default="front,back,left,right,top,iso,hero",
                        help="comma separated: %s" % ", ".join(sorted(VIEWS)))
    parser.add_argument("--turntable", type=int, default=0, help="number of turntable frames (0 = off)")
    parser.add_argument("--clay", action="store_true", help="additional clay pass with Workbench")
    parser.add_argument("--wireframe", action="store_true", help="additional wireframe pass with Workbench")
    parser.add_argument("--resolution", default="1600", help="long side in px, or WxH")
    parser.add_argument("--engine", default="auto", choices=["auto", "cycles", "eevee", "workbench"])
    parser.add_argument("--samples", type=int, default=128)
    parser.add_argument("--hdri", default="", help="environment texture for the beauty passes")
    parser.add_argument("--strength", type=float, default=1.0, help="environment strength")
    parser.add_argument("--padding", type=float, default=1.15, help="frame padding factor")
    parser.add_argument("--lens", type=float, default=50.0, help="perspective lens in mm")
    parser.add_argument("--frame", type=int, help="scene frame to render (default: current)")
    parser.add_argument("--prefix", default="", help="file name prefix")
    parser.add_argument("--index", default="proofs-index.json", help="index file name inside --output")
    parser.add_argument("--denoise", action="store_true", default=True)
    return parser.parse_args(argv)


def pick_engine(requested):
    available = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    if requested == "cycles" and "CYCLES" in available:
        return "CYCLES"
    if requested == "workbench":
        return "BLENDER_WORKBENCH"
    if requested == "eevee":
        for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            if name in available:
                return name
    for name in ("CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        if name in available:
            return name
    return bpy.context.scene.render.engine


def resolution(spec):
    if "x" in spec.lower():
        width, height = spec.lower().split("x", 1)
        return int(width), int(height)
    side = int(spec)
    return side, side


def scope_objects(scene, args):
    objects = []
    seen = set()
    for name in [n.strip() for n in args.objects.split(",") if n.strip()]:
        obj = bpy.data.objects.get(name)
        if obj and obj.name not in seen:
            seen.add(obj.name)
            objects.append(obj)
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
                if obj.name not in seen:
                    seen.add(obj.name)
                    objects.append(obj)
    if not objects:
        objects = [obj for obj in scene.objects
                   if obj.type in GEOMETRY_TYPES and obj.visible_get()]
    return objects


def bounds(objects, scene):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    minimum = [math.inf] * 3
    maximum = [-math.inf] * 3
    for obj in objects:
        if obj.type not in GEOMETRY_TYPES:
            continue
        obj_eval = obj.evaluated_get(depsgraph)
        for corner in obj_eval.bound_box:
            world = obj_eval.matrix_world @ Vector(corner)
            for index in range(3):
                minimum[index] = min(minimum[index], world[index])
                maximum[index] = max(maximum[index], world[index])
    if not all(math.isfinite(v) for v in minimum + maximum):
        raise SystemExit("error: nothing to frame; check --collections/--objects and visibility")
    center = Vector(((minimum[0] + maximum[0]) / 2.0,
                     (minimum[1] + maximum[1]) / 2.0,
                     (minimum[2] + maximum[2]) / 2.0))
    size = Vector((maximum[0] - minimum[0], maximum[1] - minimum[1], maximum[2] - minimum[2]))
    return center, size


class StateGuard:
    """Capture and restore every scene setting this script touches."""

    def __init__(self, scene, objects):
        self.scene = scene
        self.objects = objects
        self.camera = scene.camera
        self.frame = scene.frame_current
        render = scene.render
        self.render = {
            "engine": render.engine,
            "resolution_x": render.resolution_x,
            "resolution_y": render.resolution_y,
            "resolution_percentage": render.resolution_percentage,
            "filepath": render.filepath,
            "file_format": render.image_settings.file_format,
            "color_mode": render.image_settings.color_mode,
            "color_depth": render.image_settings.color_depth,
            "film_transparent": render.film_transparent,
        }
        self.world = scene.world
        self.display = {
            "light": scene.display.shading.light,
            "color_type": scene.display.shading.color_type,
            "single_color": tuple(scene.display.shading.single_color),
            "show_cavity": scene.display.shading.show_cavity,
            "show_object_outline": scene.display.shading.show_object_outline,
        }
        self.cycles_samples = getattr(scene.cycles, "samples", None) if hasattr(scene, "cycles") else None
        self.eevee_samples = getattr(scene.eevee, "taa_render_samples", None) if hasattr(scene, "eevee") else None
        self.display_types = {obj.name: obj.display_type for obj in objects}
        self.created = []

    def track(self, datablock):
        self.created.append(datablock)
        return datablock

    def restore(self):
        scene = self.scene
        render = scene.render
        for key, value in self.render.items():
            if key == "file_format":
                render.image_settings.file_format = value
            elif key == "color_mode":
                render.image_settings.color_mode = value
            elif key == "color_depth":
                render.image_settings.color_depth = value
            else:
                try:
                    setattr(render, key, value)
                except (AttributeError, TypeError):
                    pass
        scene.world = self.world
        scene.camera = self.camera
        scene.frame_set(self.frame)
        shading = scene.display.shading
        shading.light = self.display["light"]
        shading.color_type = self.display["color_type"]
        shading.single_color = self.display["single_color"]
        shading.show_cavity = self.display["show_cavity"]
        shading.show_object_outline = self.display["show_object_outline"]
        if self.cycles_samples is not None and hasattr(scene, "cycles"):
            scene.cycles.samples = self.cycles_samples
        if self.eevee_samples is not None and hasattr(scene, "eevee"):
            scene.eevee.taa_render_samples = self.eevee_samples
        for obj in self.objects:
            if obj.name in self.display_types:
                obj.display_type = self.display_types[obj.name]
        for datablock in reversed(self.created):
            try:
                if isinstance(datablock, bpy.types.Object):
                    bpy.data.objects.remove(datablock, do_unlink=True)
                elif isinstance(datablock, bpy.types.World):
                    bpy.data.worlds.remove(datablock, do_unlink=False)
                elif isinstance(datablock, bpy.types.Camera):
                    bpy.data.cameras.remove(datablock, do_unlink=False)
                elif isinstance(datablock, bpy.types.Light):
                    bpy.data.lights.remove(datablock, do_unlink=False)
            except (ReferenceError, RuntimeError):
                pass


def setup_world(guard, args, dark=False, cache=None):
    if cache is not None:
        cached = cache.get(dark)
        if cached is not None:
            guard.scene.world = cached
            return cached
    world = guard.track(bpy.data.worlds.new("__proofs_world_dark" if dark else "__proofs_world"))
    world.use_nodes = True
    tree = world.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    output = tree.nodes.new("ShaderNodeOutputWorld")
    background = tree.nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = args.strength
    if args.hdri and os.path.isfile(args.hdri):
        texture = tree.nodes.new("ShaderNodeTexEnvironment")
        texture.image = bpy.data.images.load(args.hdri)
        tree.links.new(texture.outputs["Color"], background.inputs["Color"])
    else:
        background.inputs["Color"].default_value = (0.05, 0.05, 0.06, 1.0) if dark else (0.55, 0.55, 0.58, 1.0)
    tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    guard.scene.world = world
    if cache is not None:
        cache[dark] = world
    return world


def setup_camera(guard, name="__proofs_camera"):
    camera_data = guard.track(bpy.data.cameras.new(name))
    camera_data.sensor_fit = "AUTO"
    obj = guard.track(bpy.data.objects.new(name, camera_data))
    guard.scene.collection.objects.link(obj)
    guard.scene.camera = obj
    return obj


def setup_lights(guard, center, size):
    fit = max(size)
    lights = []
    key = guard.track(bpy.data.lights.new("__proofs_key", "AREA"))
    key.energy = max(50.0, fit * fit * 12.0)
    key.size = fit * 1.6
    key_obj = guard.track(bpy.data.objects.new("__proofs_key", key))
    key_obj.location = center + Vector((fit * 1.2, -fit * 1.4, fit * 1.6))
    direction = (center - key_obj.location)
    key_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    fill = guard.track(bpy.data.lights.new("__proofs_fill", "AREA"))
    fill.energy = max(20.0, fit * fit * 4.0)
    fill.size = fit * 2.0
    fill_obj = guard.track(bpy.data.objects.new("__proofs_fill", fill))
    fill_obj.location = center + Vector((-fit * 1.6, -fit * 0.8, fit * 0.6))
    fill_obj.rotation_euler = (center - fill_obj.location).to_track_quat("-Z", "Y").to_euler()
    for item in (key_obj, fill_obj):
        guard.scene.collection.objects.link(item)
        lights.append(item)
    return lights


def aim_camera(camera, location, target, ortho_scale=None, lens=None):
    direction = target - location
    if direction.length < 1e-9:
        direction = Vector((0.0, 1.0, 0.0))
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = direction.normalized().to_track_quat("-Z", "Y")
    camera.location = location
    if ortho_scale is not None:
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = ortho_scale
        camera.data.clip_start = max(0.001, ortho_scale * 0.001)
        camera.data.clip_end = max(1000.0, direction.length + ortho_scale * 10.0)
    if lens is not None:
        camera.data.type = "PERSP"
        camera.data.lens = lens
        camera.data.clip_start = max(0.001, direction.length * 0.001)
        camera.data.clip_end = max(1000.0, direction.length * 10.0)


def configure_render(scene, engine, res, samples, filepath):
    render = scene.render
    render.engine = engine
    render.resolution_x, render.resolution_y = res
    render.resolution_percentage = 100
    render.image_settings.file_format = "PNG"
    render.image_settings.color_mode = "RGBA"
    render.image_settings.color_depth = "8"
    render.filepath = filepath
    if engine == "CYCLES":
        scene.cycles.samples = samples
        try:
            scene.cycles.use_denoising = True
        except (AttributeError, TypeError):
            pass
        if scene.cycles.device != "GPU":
            try:
                scene.cycles.device = "GPU"
            except (AttributeError, TypeError):
                pass
    elif engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.eevee.taa_render_samples = samples
        except (AttributeError, TypeError):
            pass


def workbench_settings(scene, clay=True):
    shading = scene.display.shading
    shading.light = "STUDIO"
    if clay:
        shading.color_type = "SINGLE"
        shading.single_color = (0.48, 0.48, 0.5)
    else:
        shading.color_type = "MATERIAL"
    shading.show_cavity = True
    shading.show_object_outline = True
    try:
        shading.cavity_type = "BOTH"
    except (AttributeError, TypeError):
        pass


def render(scene, path):
    bpy.context.view_layer.update()
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("  rendered %s" % path)


def main():
    args = cli_args()
    scene = bpy.context.scene
    if args.frame is not None:
        scene.frame_set(args.frame)
    objects = scope_objects(scene, args)
    if not objects:
        raise SystemExit("error: no objects in scope")
    center, size = bounds(objects, scene)
    fit = max(size.x, size.y, size.z)
    if fit <= 0:
        raise SystemExit("error: zero size bounding box; nothing to frame")

    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)
    res = resolution(args.resolution)
    engine = pick_engine(args.engine)
    guard = StateGuard(scene, objects)
    index = {
        "tool": "render_proofs.py",
        "version": TOOL_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source_file": bpy.data.filepath,
        "frame": int(scene.frame_current),
        "engine": engine,
        "resolution": list(res),
        "samples": args.samples,
        "bbox_scene_units": [round(size.x, 6), round(size.y, 6), round(size.z, 6)],
        "center_scene_units": [round(center.x, 6), round(center.y, 6), round(center.z, 6)],
        "scope": [obj.name for obj in objects][:400],
        "images": [],
        "note": "The blend file was not saved; all cameras, lights and worlds were temporary.",
    }

    views = [v.strip() for v in args.views.split(",") if v.strip()]
    unknown = [v for v in views if v not in VIEWS]
    if unknown:
        raise SystemExit("error: unknown view(s): %s (available: %s)" % (", ".join(unknown), ", ".join(sorted(VIEWS))))

    try:
        camera = setup_camera(guard)
        setup_lights(guard, center, size)
        worlds = {}

        passes = []
        for view in views:
            passes.append((view, engine, False, "%s%s" % (args.prefix, view)))
            if args.clay:
                passes.append((view, "BLENDER_WORKBENCH", True, "%sclay_%s" % (args.prefix, view)))

        for view, pass_engine, clay, name in passes:
            direction = VIEWS[view].normalized()
            if pass_engine == "BLENDER_WORKBENCH":
                setup_world(guard, args, dark=True, cache=worlds)
                configure_render(scene, "BLENDER_WORKBENCH", res, 16, "")
                workbench_settings(scene, clay=clay)
            else:
                setup_world(guard, args, cache=worlds)
                configure_render(scene, pass_engine, res, args.samples, "")
            if view in ORTHO_VIEWS:
                perpendicular = [size[i] for i in range(3) if abs(direction[i]) < 0.5]
                span = max(perpendicular) if perpendicular else fit
                ortho_scale = span * args.padding
                location = center + direction * (fit * 5.0 + 1.0)
                aim_camera(camera, location, center, ortho_scale=ortho_scale)
            else:
                fov = 2.0 * math.atan(12.0 / args.lens)
                distance = (fit * args.padding * 0.5) / math.tan(fov * 0.5)
                location = center + direction * distance
                aim_camera(camera, location, center, lens=args.lens)
            path = os.path.join(out_dir, name + ".png")
            render(scene, path)
            index["images"].append({
                "path": os.path.relpath(path, out_dir).replace(os.sep, "/"),
                "kind": "clay" if clay else ("silhouette" if view in ORTHO_VIEWS else "hero"),
                "view": view,
                "engine": scene.render.engine,
                "ortho": view in ORTHO_VIEWS,
                "camera_location": [round(v, 4) for v in camera.location],
                "ortho_scale": round(camera.data.ortho_scale, 4) if camera.data.type == "ORTHO" else None,
                "lens": round(camera.data.lens, 2) if camera.data.type == "PERSP" else None,
            })

        if args.wireframe:
            setup_world(guard, args, dark=True, cache=worlds)
            configure_render(scene, "BLENDER_WORKBENCH", res, 16, "")
            workbench_settings(scene, clay=False)
            for obj in objects:
                obj.display_type = "WIRE"
            direction = VIEWS["iso"].normalized()
            fov = 2.0 * math.atan(12.0 / args.lens)
            distance = (fit * args.padding * 0.5) / math.tan(fov * 0.5)
            aim_camera(camera, center + direction * distance, center, lens=args.lens)
            path = os.path.join(out_dir, args.prefix + "wireframe_iso.png")
            render(scene, path)
            index["images"].append({"path": os.path.relpath(path, out_dir).replace(os.sep, "/"),
                                    "kind": "wireframe", "view": "iso", "engine": "BLENDER_WORKBENCH"})
            for obj in objects:
                obj.display_type = guard.display_types.get(obj.name, "TEXTURED")

        if args.turntable and args.turntable > 1:
            turn_dir = os.path.join(out_dir, "turntable")
            os.makedirs(turn_dir, exist_ok=True)
            setup_world(guard, args, cache=worlds)
            configure_render(scene, engine if engine != "BLENDER_WORKBENCH" else pick_engine("auto"), res, args.samples, "")
            radius = fit * 0.95 * args.padding
            height = center.z + size.z * 0.12
            for step in range(args.turntable):
                angle = 2.0 * math.pi * step / args.turntable
                location = Vector((center.x + radius * math.cos(angle),
                                   center.y + radius * math.sin(angle),
                                   height))
                aim_camera(camera, location, center, lens=args.lens)
                path = os.path.join(turn_dir, "frame_%03d.png" % step)
                render(scene, path)
                index["images"].append({"path": os.path.relpath(path, out_dir).replace(os.sep, "/"),
                                        "kind": "turntable", "view": "turntable_%03d" % step,
                                        "angle_deg": round(math.degrees(angle), 2),
                                        "engine": scene.render.engine})
    finally:
        guard.restore()
        index_path = os.path.join(out_dir, args.index)
        with open(index_path, "w", encoding="utf-8") as handle:
            json.dump(index, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print("render_proofs %s: %d image(s), index %s" % (TOOL_VERSION, len(index["images"]), index_path))
        print("  the blend file was NOT saved; scene settings restored")


if __name__ == "__main__":
    main()
