"""Shared bpy helpers for the procedural WWII Soviet arms assets.

The module is intentionally dependency-free outside Blender. Geometry is built as
editable meshes with named collections, UVs, PBR image textures and real hollow
passages. It creates visual art assets only, not manufacturing geometry.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, Sequence

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
TEXTURE_SETS = ("BluedSteel", "ParkerizedSteel", "Wood", "Bakelite", "Brass", "Glass")


# -----------------------------------------------------------------------------
# Scene, collections, materials
# -----------------------------------------------------------------------------

def reset_scene(slug: str) -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = slug
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 36
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -0.25
    try:
        scene.view_settings.look = "Medium High Contrast"
    except (TypeError, ValueError):
        pass
    scene.frame_start = 1
    scene.frame_end = 1
    scene.frame_set(1)
    bpy.context.preferences.filepaths.save_version = 0
    return scene


def collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    col = bpy.data.collections.new(name)
    if parent is None:
        bpy.context.scene.collection.children.link(col)
    else:
        parent.children.link(col)
    return col


def move_to(obj: bpy.types.Object, col: bpy.types.Collection) -> bpy.types.Object:
    for existing in list(obj.users_collection):
        existing.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def set_smooth(obj: bpy.types.Object, smooth: bool = True) -> None:
    if obj.type == "MESH":
        for poly in obj.data.polygons:
            poly.use_smooth = smooth


def bevel(obj: bpy.types.Object, width: float, segments: int = 3, angle_deg: float = 28.0) -> None:
    if obj.type != "MESH" or width <= 0:
        return
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle_deg)
    try:
        mod.loop_slide = True
    except AttributeError:
        pass
    weighted = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    try:
        weighted.keep_sharp = True
        weighted.weight = 50
        weighted.mode = "FACE_AREA"
    except (AttributeError, TypeError):
        pass


def assign(obj: bpy.types.Object, material: bpy.types.Material | None) -> None:
    if material is not None and obj.type == "MESH":
        obj.data.materials.append(material)


def load_texture(slug: str, set_name: str, map_name: str) -> bpy.types.Image:
    filename = f"T_{slug}_{set_name}_{map_name}_1k.png"
    path = ASSETS / slug / "textures" / filename
    if not path.is_file():
        raise FileNotFoundError(path)
    image = bpy.data.images.load(str(path), check_existing=True)
    image.name = filename
    image.colorspace_settings.name = "sRGB" if map_name == "BaseColor" else "Non-Color"
    # Texture files are delivered alongside the .blend. Keep a portable relative
    # path instead of packing 30 full-size images into every source file.
    image.filepath = f"//../textures/{filename}"
    return image


def pbr_material(slug: str, set_name: str, *, metallic_bias: float = 0.0,
                 roughness_bias: float = 0.0, transmission: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(f"M_{slug}_{set_name}")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (720, 80)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (450, 80)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    uv.location = (-900, 100)

    def image_node(map_name: str, x: float, y: float) -> bpy.types.Node:
        node = nodes.new("ShaderNodeTexImage")
        node.name = f"{set_name}_{map_name}"
        node.label = f"{set_name} {map_name}"
        node.image = load_texture(slug, set_name, map_name)
        node.image.colorspace_settings.name = "sRGB" if map_name == "BaseColor" else "Non-Color"
        node.extension = "REPEAT"
        node.interpolation = "Linear"
        node.location = (x, y)
        links.new(uv.outputs["UV"], node.inputs["Vector"])
        return node

    base = image_node("BaseColor", -650, 320)
    rough = image_node("Roughness", -650, 20)
    metal = image_node("Metallic", -650, -280)
    normal_tex = image_node("Normal", -650, -580)
    ao = image_node("AO", -650, -860)

    multiply = nodes.new("ShaderNodeMixRGB")
    multiply.blend_type = "MULTIPLY"
    multiply.inputs[0].default_value = 0.18
    multiply.location = (-170, 320)
    links.new(base.outputs["Color"], multiply.inputs[1])
    links.new(ao.outputs["Color"], multiply.inputs[2])
    links.new(multiply.outputs["Color"], bsdf.inputs["Base Color"])

    rough_math = nodes.new("ShaderNodeMath")
    rough_math.operation = "ADD"
    rough_math.inputs[1].default_value = roughness_bias
    rough_math.location = (-170, 20)
    links.new(rough.outputs["Color"], rough_math.inputs[0])
    links.new(rough_math.outputs["Value"], bsdf.inputs["Roughness"])

    metal_math = nodes.new("ShaderNodeMath")
    metal_math.operation = "ADD"
    metal_math.inputs[1].default_value = metallic_bias
    metal_math.location = (-170, -280)
    links.new(metal.outputs["Color"], metal_math.inputs[0])
    links.new(metal_math.outputs["Value"], bsdf.inputs["Metallic"])

    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.location = (-170, -580)
    normal_map.inputs["Strength"].default_value = 0.32 if set_name in {"Wood", "Bakelite"} else 0.20
    links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
    links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])

    if transmission > 0:
        trans_input = bsdf.inputs.get("Transmission Weight") or bsdf.inputs.get("Transmission")
        if trans_input:
            trans_input.default_value = transmission
        ior = bsdf.inputs.get("IOR")
        if ior:
            ior.default_value = 1.5
    return mat


def simple_material(name: str, rgb: Sequence[float], *, metallic: float = 0.0,
                    roughness: float = 0.5, transmission: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    trans_input = bsdf.inputs.get("Transmission Weight") or bsdf.inputs.get("Transmission")
    if transmission and trans_input:
        trans_input.default_value = transmission
        if bsdf.inputs.get("IOR"):
            bsdf.inputs["IOR"].default_value = 1.5
    return mat


# -----------------------------------------------------------------------------
# Mesh primitives
# -----------------------------------------------------------------------------

def mesh_object(name: str, vertices: Sequence[Sequence[float]], faces: Sequence[Sequence[int]],
                col: bpy.types.Collection, material: bpy.types.Material | None = None,
                smooth_faces: Iterable[bool] | None = None) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata([tuple(map(float, v)) for v in vertices], [], [tuple(f) for f in faces])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    assign(obj, material)
    # Recalculate normals from a consistent closed surface.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    if smooth_faces is not None:
        for poly, flag in zip(mesh.polygons, smooth_faces):
            poly.use_smooth = bool(flag)
    return obj


def revolved_tube(name: str, profile: Sequence[tuple[float, float, float]], *,
                  col: bpy.types.Collection, material: bpy.types.Material | None,
                  segments: int = 64, location: Sequence[float] = (0, 0, 0)) -> bpy.types.Object:
    """Hollow lathe around +X. profile = [(x, outer_radius, inner_radius), ...]."""
    verts: list[tuple[float, float, float]] = []
    for x, outer, inner in profile:
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            verts.append((x, outer * math.cos(a), outer * math.sin(a)))
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            verts.append((x, inner * math.cos(a), inner * math.sin(a)))
    faces: list[tuple[int, ...]] = []
    smooth: list[bool] = []
    ring = 2 * segments

    def o(k: int, i: int) -> int:
        return k * ring + (i % segments)

    def inn(k: int, i: int) -> int:
        return k * ring + segments + (i % segments)

    for k in range(len(profile) - 1):
        for i in range(segments):
            j = i + 1
            faces.append((o(k, i), o(k, j), o(k + 1, j), o(k + 1, i)))
            smooth.append(True)
            faces.append((inn(k + 1, i), inn(k + 1, j), inn(k, j), inn(k, i)))
            smooth.append(True)
    # Annular caps at both ends only: the bore stays open.
    for i in range(segments):
        j = i + 1
        faces.append((o(0, j), o(0, i), inn(0, i), inn(0, j)))
        smooth.append(False)
        last = len(profile) - 1
        faces.append((o(last, i), o(last, j), inn(last, j), inn(last, i)))
        smooth.append(False)
    obj = mesh_object(name, verts, faces, col, material, smooth)
    obj.location = location
    return obj


def profile_extrude(name: str, points_xz: Sequence[tuple[float, float]], width: float, *,
                    col: bpy.types.Collection, material: bpy.types.Material | None,
                    location: Sequence[float] = (0, 0, 0)) -> bpy.types.Object:
    """Extrude a closed XZ polygon along Y; points are local to the object."""
    n = len(points_xz)
    verts: list[tuple[float, float, float]] = []
    for x, z in points_xz:
        verts.append((x, -width / 2.0, z))
    for x, z in points_xz:
        verts.append((x, width / 2.0, z))
    faces: list[tuple[int, ...]] = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    obj = mesh_object(name, verts, faces, col, material)
    obj.location = location
    return obj


def box(name: str, size: Sequence[float], location: Sequence[float], *,
        col: bpy.types.Collection, material: bpy.types.Material | None,
        bevel_width: float = 0.0, rotation: Sequence[float] = (0, 0, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to(obj, col)
    assign(obj, material)
    if bevel_width:
        bevel(obj, bevel_width)
    set_smooth(obj, True)
    return obj


def cylinder(name: str, radius: float, depth: float, location: Sequence[float], *,
             col: bpy.types.Collection, material: bpy.types.Material | None,
             axis: str = "Z", vertices: int = 48, bevel_width: float = 0.0) -> bpy.types.Object:
    rotations = {"Z": (0, 0, 0), "X": (0, math.pi / 2, 0), "Y": (math.pi / 2, 0, 0)}
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                        location=location, rotation=rotations[axis])
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    move_to(obj, col)
    assign(obj, material)
    set_smooth(obj, True)
    if bevel_width:
        bevel(obj, bevel_width)
    return obj


def sphere(name: str, radius: float, location: Sequence[float], *,
           col: bpy.types.Collection, material: bpy.types.Material | None,
           segments: int = 24, rings: int = 12) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings,
                                         radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    move_to(obj, col)
    assign(obj, material)
    set_smooth(obj, True)
    return obj


def torus(name: str, major_radius: float, minor_radius: float, location: Sequence[float], *,
          col: bpy.types.Collection, material: bpy.types.Material | None,
          axis: str = "Z", major_segments: int = 40, minor_segments: int = 12) -> bpy.types.Object:
    rotations = {"Z": (0, 0, 0), "X": (0, math.pi / 2, 0), "Y": (math.pi / 2, 0, 0)}
    bpy.ops.mesh.primitive_torus_add(major_segments=major_segments, minor_segments=minor_segments,
                                     major_radius=major_radius, minor_radius=minor_radius,
                                     location=location, rotation=rotations[axis])
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    move_to(obj, col)
    assign(obj, material)
    set_smooth(obj, True)
    return obj


def rounded_cutter(name: str, size: Sequence[float], location: Sequence[float], *,
                   col: bpy.types.Collection, bevel_width: float) -> bpy.types.Object:
    obj = box(name, size, location, col=col, material=None)
    bevel(obj, bevel_width, segments=3, angle_deg=1)
    # Apply the bevel so the Boolean sees the rounded cutter volume.
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for mod in list(obj.modifiers):
        if mod.type == "BEVEL":
            bpy.ops.object.modifier_apply(modifier=mod.name)
        else:
            obj.modifiers.remove(mod)
    set_smooth(obj, True)
    return obj


def apply_boolean(target: bpy.types.Object, cutters: Sequence[bpy.types.Object], name: str) -> None:
    if not cutters:
        return
    for obj in cutters:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    for obj in cutters:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = cutters[0]
    bpy.ops.object.join()
    cutter = bpy.context.object
    cutter.name = name + "_Cutter"
    mod = target.modifiers.new(name, "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def curve_tube(name: str, points: Sequence[Sequence[float]], thickness: float, *,
               col: bpy.types.Collection, material: bpy.types.Material | None,
               cyclic: bool = False, bevel_resolution: int = 3) -> bpy.types.Object:
    curve = bpy.data.curves.new(name + "_Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 12
    curve.bevel_depth = thickness
    curve.bevel_resolution = bevel_resolution
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, coords in zip(spline.points, points):
        point.co = (*coords, 1.0)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    col.objects.link(obj)
    assign(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    obj.name = name
    set_smooth(obj, True)
    return obj


def oval_loop(name: str, center: Sequence[float], radius_x: float, radius_z: float, thickness: float,
              *, col: bpy.types.Collection, material: bpy.types.Material | None,
              steps: int = 36) -> bpy.types.Object:
    cx, cy, cz = center
    points = [
        (cx + radius_x * math.cos(2 * math.pi * i / steps), cy,
         cz + radius_z * math.sin(2 * math.pi * i / steps))
        for i in range(steps)
    ]
    return curve_tube(name, points, thickness, col=col, material=material, cyclic=True)


def helix(name: str, center: Sequence[float], radius: float, length: float, turns: float,
          wire: float, *, axis: str = "X", col: bpy.types.Collection,
          material: bpy.types.Material | None, steps: int = 160) -> bpy.types.Object:
    cx, cy, cz = center
    points = []
    for i in range(steps + 1):
        t = i / steps
        angle = 2 * math.pi * turns * t
        if axis == "X":
            points.append((cx + (t - 0.5) * length, cy + radius * math.cos(angle), cz + radius * math.sin(angle)))
        elif axis == "Y":
            points.append((cx + radius * math.cos(angle), cy + (t - 0.5) * length, cz + radius * math.sin(angle)))
        else:
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle), cz + (t - 0.5) * length))
    return curve_tube(name, points, wire, col=col, material=material, cyclic=False)


def screw(name: str, location: Sequence[float], *, axis: str, col: bpy.types.Collection,
          head: bpy.types.Material | None, slot: bpy.types.Material | None,
          radius: float = 0.0026, depth: float = 0.0015) -> list[bpy.types.Object]:
    parts = [cylinder(name + "_Head", radius, depth, location, col=col, material=head,
                      axis=axis, vertices=24, bevel_width=0.00025)]
    x, y, z = location
    if axis == "Y":
        parts.append(box(name + "_Slot", (radius * 1.35, 0.00035, 0.00055),
                         (x, y - depth * 0.56, z), col=col, material=slot))
    elif axis == "Z":
        parts.append(box(name + "_Slot", (radius * 1.35, 0.00055, 0.00035),
                         (x, y, z + depth * 0.56), col=col, material=slot))
    else:
        parts.append(box(name + "_Slot", (0.00035, radius * 1.35, 0.00055),
                         (x + depth * 0.56, y, z), col=col, material=slot))
    return parts


def text_marking(name: str, text: str, location: Sequence[float], *,
                 col: bpy.types.Collection, material: bpy.types.Material | None,
                 size: float = 0.006, rotation: Sequence[float] = (math.pi / 2, 0, 0)) -> bpy.types.Object:
    curve = bpy.data.curves.new(name + "_Curve", "FONT")
    curve.body = text
    curve.size = size
    curve.extrude = 0.00018
    curve.bevel_depth = 0.00004
    curve.bevel_resolution = 1
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    obj = bpy.data.objects.new(name, curve)
    obj.location = location
    obj.rotation_euler = rotation
    col.objects.link(obj)
    assign(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    obj.name = name
    return obj


def pivot_control(obj: bpy.types.Object, pivot: Sequence[float], name: str,
                  col: bpy.types.Collection) -> bpy.types.Object:
    return control_group([obj], pivot, name, col)


def control_group(objects: Sequence[bpy.types.Object], pivot: Sequence[float], name: str,
                  col: bpy.types.Collection) -> bpy.types.Object:
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.008
    empty.location = pivot
    col.objects.link(empty)
    empty["controlled_objects"] = ", ".join(obj.name for obj in objects)
    bpy.context.view_layer.update()
    parent_inverse = empty.matrix_world.inverted()
    for obj in objects:
        obj.parent = empty
        obj.matrix_parent_inverse = parent_inverse
        obj["pivot_mm"] = [round(float(v) * 1000.0, 3) for v in pivot]
    bpy.context.view_layer.update()
    return empty


# -----------------------------------------------------------------------------
# Normalisation, UV, studio and statistics
# -----------------------------------------------------------------------------

def model_meshes(collections: Sequence[bpy.types.Collection]) -> list[bpy.types.Object]:
    seen: set[str] = set()
    result: list[bpy.types.Object] = []
    for col in collections:
        for obj in col.all_objects:
            if obj.type == "MESH" and obj.name not in seen:
                seen.add(obj.name)
                result.append(obj)
    return result


def world_bbox(objects: Sequence[bpy.types.Object], evaluated: bool = False) -> tuple[Vector, Vector]:
    depsgraph = bpy.context.evaluated_depsgraph_get() if evaluated else None
    low = Vector((math.inf, math.inf, math.inf))
    high = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        if obj.type != "MESH":
            continue
        if evaluated:
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = obj_eval.to_mesh()
            matrix = obj_eval.matrix_world
        else:
            mesh = obj.data
            matrix = obj.matrix_world
        try:
            for vertex in mesh.vertices:
                p = matrix @ vertex.co
                for axis in range(3):
                    low[axis] = min(low[axis], p[axis])
                    high[axis] = max(high[axis], p[axis])
        finally:
            if evaluated:
                obj_eval.to_mesh_clear()
    return low, high


def normalize_length(objects: Sequence[bpy.types.Object], target_length: float) -> float:
    low, high = world_bbox(objects, evaluated=False)
    current = high.x - low.x
    if current <= 0:
        raise RuntimeError("cannot normalize an empty model")
    factor = target_length / current
    for obj in objects:
        if obj.type != "MESH":
            continue
        for vertex in obj.data.vertices:
            vertex.co *= factor
        obj.location *= factor
        for mod in obj.modifiers:
            if mod.type == "BEVEL":
                mod.width *= factor
            elif mod.type == "SOLIDIFY":
                mod.thickness *= factor
        obj.data.update()
    bpy.context.view_layer.update()
    return factor


def smart_uv_all(objects: Sequence[bpy.types.Object]) -> None:
    meshes = [obj for obj in objects if obj.type == "MESH" and obj.data.vertices]
    if not meshes:
        return
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.012, correct_aspect=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")


def create_studio(slug: str, bbox_low: Vector, bbox_high: Vector) -> bpy.types.Collection:
    studio = collection(f"{slug}_Studio")
    center = (bbox_low + bbox_high) / 2.0
    size = max(bbox_high - bbox_low)
    floor_mat = simple_material(f"M_{slug}_StudioFloor", (0.048, 0.050, 0.054), roughness=0.86)

    bpy.ops.mesh.primitive_plane_add(size=size * 4.0,
                                     location=(center.x, center.y, bbox_low.z - size * 0.08))
    floor = bpy.context.object
    floor.name = f"{slug}_StudioFloor"
    move_to(floor, studio)
    assign(floor, floor_mat)

    world = bpy.data.worlds.new(f"{slug}_StudioWorld")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.055, 0.058, 0.065, 1.0)
        background.inputs["Strength"].default_value = 0.42
    bpy.context.scene.world = world

    def area(name: str, location: Vector, energy: float, light_size: float) -> None:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = light_size
        obj = bpy.data.objects.new(name, data)
        studio.objects.link(obj)
        obj.location = location
        obj.rotation_euler = (center - location).to_track_quat("-Z", "Y").to_euler()

    area(f"{slug}_Key", center + Vector((size * 0.9, -size * 1.2, size * 1.0)), max(35, size * 150), size * 1.2)
    area(f"{slug}_Fill", center + Vector((-size * 1.1, -size * 0.6, size * 0.5)), max(18, size * 65), size * 1.5)
    area(f"{slug}_Rim", center + Vector((size * 0.1, size * 1.1, size * 0.9)), max(24, size * 95), size * 1.0)

    camera_data = bpy.data.cameras.new(f"{slug}_Camera")
    camera = bpy.data.objects.new(f"{slug}_Camera", camera_data)
    studio.objects.link(camera)
    camera.location = center + Vector((size * 0.85, -size * 1.15, size * 0.42))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.lens = 50
    camera_data.clip_start = max(0.001, size * 0.001)
    camera_data.clip_end = size * 50
    bpy.context.scene.camera = camera

    # Hidden 100 mm scale reference; useful for manual inspection but excluded from renders.
    scale_mat = simple_material(f"M_{slug}_ScaleRef", (0.75, 0.72, 0.62), roughness=0.7)
    scale_bar = box(f"{slug}_ScaleRef_100mm", (0.1, 0.003, 0.004),
                    (center.x, center.y + size * 0.35, bbox_low.z - size * 0.05),
                    col=studio, material=scale_mat, bevel_width=0.0004)
    scale_bar.hide_render = True
    scale_bar.hide_set(True)
    return studio


def triangle_count(objects: Sequence[bpy.types.Object]) -> int:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    count = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            count += sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons)
        finally:
            evaluated.to_mesh_clear()
    return count


def save_blend(slug: str, stats: dict) -> Path:
    path = ASSETS / slug / "source" / f"{slug}.blend"
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    stats_path = ASSETS / slug / "manifest" / "build-stats.json"
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
