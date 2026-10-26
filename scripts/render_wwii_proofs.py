#!/usr/bin/env python3
"""Render Cycles proof views for each generated .blend file.

Run with the headless bpy interpreter, e.g.

    python scripts/render_wwii_proofs.py --only ppsh-41

It never modifies the saved .blend. Intermediate turntable frames are written to
/tmp and assembled into an animated GIF with Pillow.
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SLUGS = ("ppsh-41", "mosin-m91-30", "mosin-m91-30-pu", "nagant-m1895")
STILL_SAMPLES = 20
TURNTABLE_SAMPLES = 6
STILL_RESOLUTION = (1280, 720)
TURNTABLE_RESOLUTION = (560, 320)
TURNTABLE_FRAMES = 10


def model_bbox(scene: bpy.types.Scene) -> tuple[Vector, Vector, Vector]:
    name = scene.get("model_collection")
    col = bpy.data.collections.get(name) if name else None
    if col is None:
        col = bpy.data.collections.get(f"{scene.name}_Model")
    objects = [o for o in col.all_objects if o.type == "MESH"] if col else []
    if not objects:
        raise RuntimeError(f"no mesh objects in model collection {name}")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    low = Vector((math.inf, math.inf, math.inf))
    high = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            for vertex in mesh.vertices:
                p = evaluated.matrix_world @ vertex.co
                for axis in range(3):
                    low[axis] = min(low[axis], p[axis])
                    high[axis] = max(high[axis], p[axis])
        finally:
            evaluated.to_mesh_clear()
    center = (low + high) / 2.0
    return low, high, center


def camera(scene: bpy.types.Scene, name: str, location: Vector, target: Vector, *,
           ortho_scale: float | None = None, lens: float = 50.0) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()
    if ortho_scale is not None:
        data.type = "ORTHO"
        data.ortho_scale = ortho_scale
    else:
        data.type = "PERSP"
        data.lens = lens
    data.clip_start = 0.0005
    data.clip_end = 200.0
    scene.camera = obj
    bpy.context.view_layer.update()
    return obj


def render_still(scene: bpy.types.Scene, output: Path, cam: bpy.types.Object, *,
                 resolution: tuple[int, int], samples: int) -> None:
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.cycles.samples = samples
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(output)
    scene.camera = cam
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print(f"render: {output.name}")


def fit_scale(width: float, height: float, aspect: float, margin: float = 1.14) -> float:
    """Blender's ortho_scale is the horizontal width of the camera frame."""
    return max(width * margin, height * aspect * margin)


def bbox_corners(low: Vector, high: Vector) -> list[Vector]:
    return [Vector((x, y, z)) for x in (low.x, high.x)
            for y in (low.y, high.y) for z in (low.z, high.z)]


def fit_ortho_camera(obj: bpy.types.Object, target: Vector, low: Vector, high: Vector,
                     aspect: float, margin: float = 1.14) -> None:
    """Fit an orthographic camera to the projected bounding box and centre it."""
    obj.data.type = "ORTHO"
    quat = obj.rotation_euler.to_quaternion()
    right = quat @ Vector((1, 0, 0))
    up = quat @ Vector((0, 1, 0))
    projections = [((corner - target).dot(right), (corner - target).dot(up))
                   for corner in bbox_corners(low, high)]
    xs = [p[0] for p in projections]
    ys = [p[1] for p in projections]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    shift = right * ((min(xs) + max(xs)) / 2.0) + up * ((min(ys) + max(ys)) / 2.0)
    obj.location += shift
    obj.data.ortho_scale = fit_scale(width, height, aspect, margin)
    bpy.context.view_layer.update()


def render_asset(slug: str) -> dict:
    blend = ASSETS / slug / "source" / f"{slug}.blend"
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.use_denoising = True
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -0.25
    try:
        scene.view_settings.look = "Medium High Contrast"
    except (TypeError, ValueError):
        pass

    low, high, center = model_bbox(scene)
    size = high - low
    max_size = max(size)
    renders = ASSETS / slug / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    aspect = STILL_RESOLUTION[0] / STILL_RESOLUTION[1]
    distance = max_size * 2.2

    proof_paths: dict[str, Path] = {}

    # Hero: fitted orthographic 3/4 view generated for every render pass.
    hero_location = center + Vector((max_size * 0.46, -max_size * 1.55, max_size * 0.52))
    hero_camera = camera(scene, f"{slug}_HeroCamera", hero_location, center, lens=45)
    fit_ortho_camera(hero_camera, center, low, high, aspect, margin=1.16)
    hero_path = renders / "hero.png"
    render_still(scene, hero_path, hero_camera, resolution=STILL_RESOLUTION, samples=STILL_SAMPLES)
    proof_paths["hero"] = hero_path

    # Right side (the user-facing side with ejection port / bolt handle).
    side_scale = fit_scale(size.x, size.z, aspect, margin=1.18)
    right = camera(scene, f"{slug}_RightCamera", center + Vector((0, -distance, 0)), center,
                   ortho_scale=side_scale)
    fit_ortho_camera(right, center, low, high, aspect, margin=1.18)
    right_path = renders / "silhouette_right.png"
    render_still(scene, right_path, right, resolution=STILL_RESOLUTION, samples=STILL_SAMPLES)
    proof_paths["right"] = right_path

    left = camera(scene, f"{slug}_LeftCamera", center + Vector((0, distance, 0)), center,
                  ortho_scale=side_scale)
    fit_ortho_camera(left, center, low, high, aspect, margin=1.18)
    left_path = renders / "silhouette_left.png"
    render_still(scene, left_path, left, resolution=STILL_RESOLUTION, samples=STILL_SAMPLES)
    proof_paths["left"] = left_path

    top_scale = fit_scale(size.x, size.y, aspect, margin=1.20)
    top = camera(scene, f"{slug}_TopCamera", center + Vector((0, 0, distance)), center,
                 ortho_scale=top_scale)
    fit_ortho_camera(top, center, low, high, aspect, margin=1.20)
    top_path = renders / "silhouette_top.png"
    render_still(scene, top_path, top, resolution=STILL_RESOLUTION, samples=STILL_SAMPLES)
    proof_paths["top"] = top_path

    front_scale = fit_scale(size.y, size.z, aspect, margin=1.8)
    front = camera(scene, f"{slug}_MuzzleCamera",
                   center + Vector((distance, 0, 0)), center, ortho_scale=front_scale)
    fit_ortho_camera(front, center, low, high, aspect, margin=1.8)
    muzzle_path = renders / "muzzle_and_bore.png"
    render_still(scene, muzzle_path, front, resolution=STILL_RESOLUTION, samples=STILL_SAMPLES)
    proof_paths["muzzle"] = muzzle_path

    bore_target = Vector((high.x - max_size * 0.030, 0.0, 0.0))
    bore_location = Vector((high.x + max_size * 0.055, -max_size * 0.018, max_size * 0.010))
    bore_scale = max(0.022, max_size * 0.035)
    macro = camera(scene, f"{slug}_MacroBoreCamera", bore_location, bore_target,
                   ortho_scale=bore_scale)
    macro_path = renders / "macro_true_bore.png"
    render_still(scene, macro_path, macro, resolution=STILL_RESOLUTION, samples=STILL_SAMPLES)
    proof_paths["macro_bore"] = macro_path

    # Clay view: neutral material override from the hero camera.
    clay = bpy.data.materials.new(f"M_{slug}_ClayOverride")
    clay.use_nodes = True
    bsdf = clay.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.53, 0.54, 0.55, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Roughness"].default_value = 0.58
    view_layer = scene.view_layers[0]
    previous_override = view_layer.material_override
    view_layer.material_override = clay
    clay_path = renders / "clay_hero.png"
    render_still(scene, clay_path, hero_camera, resolution=STILL_RESOLUTION, samples=STILL_SAMPLES)
    proof_paths["clay"] = clay_path
    view_layer.material_override = previous_override

    # Turntable: 12 low-sample frames assembled into a GIF without ffmpeg.
    from PIL import Image
    frames = []
    with tempfile.TemporaryDirectory(prefix=f"wwii_{slug}_") as tmp:
        tmp_dir = Path(tmp)
        for i in range(TURNTABLE_FRAMES):
            angle = 2.0 * math.pi * i / TURNTABLE_FRAMES
            location = center + Vector((
                math.cos(angle) * max_size * 1.75,
                -math.sin(angle) * max_size * 1.75,
                max_size * 0.35,
            ))
            cam = camera(scene, f"{slug}_Turntable_{i:02d}", location, center, lens=45)
            frame_path = tmp_dir / f"frame_{i:02d}.png"
            render_still(scene, frame_path, cam, resolution=TURNTABLE_RESOLUTION,
                         samples=TURNTABLE_SAMPLES)
            frames.append(Image.open(frame_path).convert("RGB"))
            bpy.data.objects.remove(cam, do_unlink=True)
        gif_path = renders / "turntable.gif"
        frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                       duration=120, loop=0, optimize=True)
        proof_paths["turntable"] = gif_path

    # Machine-readable proof index.
    import json
    index = {
        "slug": slug,
        "engine": "CYCLES",
        "samples_stills": STILL_SAMPLES,
        "samples_turntable": TURNTABLE_SAMPLES,
        "still_resolution": list(STILL_RESOLUTION),
        "turntable_frames": TURNTABLE_FRAMES,
        "bbox_mm": [round(float(v) * 1000.0, 3) for v in size],
        "proofs": {key: str(path.relative_to(ROOT)).replace("\\", "/")
                   for key, path in proof_paths.items()},
    }
    (renders / "proofs-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PROOFS {slug}: {len(proof_paths)} files in {renders}")
    return index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=(*SLUGS, "all"), default="all")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    slugs = SLUGS if args.only == "all" else (args.only,)
    results = {slug: render_asset(slug) for slug in slugs}
    if args.output_json:
        import json
        Path(args.output_json).write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
