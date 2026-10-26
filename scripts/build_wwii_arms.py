#!/usr/bin/env python3
"""Build four editable high-poly visual weapon assets in Blender.

Usage (headless bpy interpreter):
    python scripts/build_wwii_arms.py --only ppsh-41

The geometry is art/reference modelling: it deliberately omits manufacturing
tolerances, functional chamber dimensions and any production instructions.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import bpy
from mathutils import Vector

from wwii_arms_lib import (
    ASSETS,
    ROOT,
    TEXTURE_SETS,
    apply_boolean,
    assign,
    bevel,
    box,
    collection,
    control_group,
    create_studio,
    curve_tube,
    cylinder,
    helix,
    mesh_object,
    model_meshes,
    move_to,
    normalize_length,
    oval_loop,
    pbr_material,
    profile_extrude,
    reset_scene,
    revolved_tube,
    rounded_cutter,
    save_blend,
    screw,
    set_smooth,
    simple_material,
    smart_uv_all,
    sphere,
    text_marking,
    torus,
    triangle_count,
    world_bbox,
)

SLUGS = ("ppsh-41", "mosin-m91-30", "mosin-m91-30-pu", "nagant-m1895")
TARGET_LENGTHS = {
    "ppsh-41": 0.843,
    "mosin-m91-30": 1.232,
    "mosin-m91-30-pu": 1.232,
    "nagant-m1895": 0.235,
}
VARIANTS = {
    "ppsh-41": "ППШ-41, поздний военный выпуск, деревянный приклад, 71-зарядный барабанный магазин, кожух ствола с вентиляционными окнами",
    "mosin-m91-30": "Винтовка Мосина обр. 1891/30, рядовая пехотная комплектация, механические прицельные приспособления",
    "mosin-m91-30-pu": "Винтовка Мосина обр. 1891/30, снайперский вариант с боковым кронштейном и оптическим прицелом ПУ 3,5×",
    "nagant-m1895": "Револьвер Нагана обр. 1895, 7-зарядный барабан, ствол 114 мм, тёмные щёчки рукояти",
}


@dataclass
class Context:
    slug: str
    root: bpy.types.Collection
    cols: dict[str, bpy.types.Collection]
    mats: dict[str, bpy.types.Material]
    pivots: list[dict] = field(default_factory=list)

    def col(self, key: str) -> bpy.types.Collection:
        return self.cols[key]

    def mat(self, key: str) -> bpy.types.Material:
        return self.mats[key]

    def pivot(self, name: str, objects: Sequence[bpy.types.Object], pivot: Sequence[float]) -> None:
        self.pivots.append({"name": f"CTRL_{self.slug}_{name}", "objects": list(objects), "pivot": tuple(pivot)})


def checkered_grip_material(slug: str) -> bpy.types.Material:
    # Dark stained grip panels. Fine checkering is represented by the separate
    # engraved grooves added to the panels; no procedural bump is used because
    # it over-brightens small curved panels under the studio area lights.
    mat = simple_material(f"M_{slug}_CheckeredGrip", (0.020, 0.011, 0.006), roughness=0.82)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        specular = bsdf.inputs.get("Specular IOR Level") or bsdf.inputs.get("Specular")
        if specular:
            specular.default_value = 0.12
    return mat


def make_materials(slug: str) -> dict[str, bpy.types.Material]:
    biases = {"BluedSteel": -0.06, "ParkerizedSteel": 0.04, "Brass": -0.04}
    mats = {
        name: pbr_material(
            slug, name,
            roughness_bias=biases.get(name, 0.0),
            transmission=0.82 if name == "Glass" else 0.0,
        )
        for name in TEXTURE_SETS
    }
    # Small biases distinguish the six source maps without breaking PBR ranges.
    mats["DarkSteel"] = simple_material(f"M_{slug}_DarkSteel", (0.008, 0.009, 0.011), metallic=0.8, roughness=0.62)
    mats["BoreShadow"] = simple_material(f"M_{slug}_BoreShadow", (0.0015, 0.0018, 0.0022), roughness=0.9)
    mats["BrightSteel"] = simple_material(f"M_{slug}_BrightSteel", (0.125, 0.135, 0.145), metallic=1.0, roughness=0.30)
    mats["Engraving"] = simple_material(f"M_{slug}_Engraving", (0.050, 0.041, 0.028), metallic=0.65, roughness=0.50)
    mats["Felt"] = simple_material(f"M_{slug}_Felt", (0.035, 0.032, 0.028), roughness=0.9)
    mats["CheckeredGrip"] = checkered_grip_material(slug)
    return mats


def make_context(slug: str) -> Context:
    root = collection(f"{slug}_Model")
    keys = ("Barrel", "Receiver", "Stock", "Sights", "Controls", "Magazine",
            "Internals", "Fasteners", "Markings", "Optics", "Cylinder")
    cols = {key: collection(f"{slug}_{key}", parent=root) for key in keys}
    return Context(slug=slug, root=root, cols=cols, mats=make_materials(slug))


def spiral_points(center: Sequence[float], radius_start: float, radius_end: float,
                  turns: float, steps: int = 240) -> list[tuple[float, float, float]]:
    cx, cy, cz = center
    result = []
    for i in range(steps + 1):
        t = i / steps
        angle = 2 * math.pi * turns * t
        radius = radius_start + (radius_end - radius_start) * t
        result.append((cx + radius * math.cos(angle), cy, cz + radius * math.sin(angle)))
    return result


# -----------------------------------------------------------------------------
# PPSh-41
# -----------------------------------------------------------------------------

def build_ppsh(ctx: Context) -> None:
    m, c = ctx.mats, ctx.cols

    barrel = revolved_tube(
        "SM_PPSh_Barrel_TrueBore",
        [(0.000, 0.0090, 0.0039), (0.045, 0.0085, 0.0039),
         (0.052, 0.0104, 0.0039), (0.062, 0.0082, 0.0039),
         (0.245, 0.0075, 0.0039), (0.269, 0.0071, 0.0039)],
        col=c["Barrel"], material=m["BluedSteel"], segments=80)
    barrel["passage"] = "barrel_bore"

    bore_shadow = revolved_tube(
        "SM_PPSh_BoreShadow", [(-0.006, 0.0043, 0.0032), (-0.004, 0.0043, 0.0032)],
        col=c["Internals"], material=m["BoreShadow"], segments=48)

    shroud = revolved_tube(
        "SM_PPSh_BarrelShroud_Vented",
        [(0.054, 0.0175, 0.0120), (0.060, 0.0182, 0.0120),
         (0.250, 0.0182, 0.0120), (0.258, 0.0172, 0.0120)],
        col=c["Barrel"], material=m["ParkerizedSteel"], segments=80)
    slot_cutters = []
    for x in (0.079, 0.113, 0.147, 0.181, 0.215, 0.242):
        slot_cutters.append(rounded_cutter(
            f"TMP_PPSh_VentSlot_{int(x * 1000):03d}", (0.023, 0.060, 0.0092),
            (x, 0.0, 0.0), col=c["Barrel"], bevel_width=0.0035))
    apply_boolean(shroud, slot_cutters, "PPSh_VentilationSlots")
    bevel(shroud, 0.0006, segments=2)

    muzzle_plate = profile_extrude(
        "SM_PPSh_MuzzleBrake_Angled",
        [(0.251, -0.022), (0.269, -0.022), (0.269, 0.024), (0.251, 0.018)],
        0.034, col=c["Barrel"], material=m["ParkerizedSteel"])
    muzzle_hole = cylinder("TMP_PPSh_MuzzleHole", 0.0094, 0.040, (0.262, 0, 0),
                           col=c["Barrel"], material=None, axis="X", vertices=64)
    apply_boolean(muzzle_plate, [muzzle_hole], "PPSh_MuzzleAperture")
    bevel(muzzle_plate, 0.0009, segments=2)
    revolved_tube("SM_PPSh_MuzzleCrown",
                  [(0.266, 0.0088, 0.0039), (0.269, 0.0088, 0.0039)],
                  col=c["Barrel"], material=m["BrightSteel"], segments=64)
    revolved_tube("SM_PPSh_BoreLiner",
                  [(0.250, 0.00386, 0.00374), (0.269, 0.00386, 0.00374)],
                  col=c["Barrel"], material=m["BoreShadow"], segments=48)

    torus("SM_PPSh_FrontSight_Hood", 0.0105, 0.0015, (0.236, 0, 0.0195),
          col=c["Sights"], material=m["BluedSteel"], axis="X")
    box("SM_PPSh_FrontSight_Post", (0.0032, 0.0032, 0.010), (0.236, 0, 0.022),
        col=c["Sights"], material=m["BrightSteel"], bevel_width=0.0004)
    box("SM_PPSh_RearSight_Base", (0.030, 0.014, 0.0032), (-0.018, 0, 0.0215),
        col=c["Sights"], material=m["BluedSteel"], bevel_width=0.0005)
    for idx, y in enumerate((-0.008, 0.008), 1):
        box(f"SM_PPSh_RearSight_Ear_{idx:02d}", (0.007, 0.003, 0.010),
            (-0.018, y, 0.027), col=c["Sights"], material=m["BluedSteel"], bevel_width=0.0005)
    box("SM_PPSh_RearSight_Leaf", (0.022, 0.012, 0.002), (-0.007, 0, 0.025),
        col=c["Sights"], material=m["BrightSteel"], bevel_width=0.0003)

    receiver = revolved_tube(
        "SM_PPSh_Receiver_Shell",
        [(-0.170, 0.0198, 0.0158), (-0.160, 0.0205, 0.0158),
         (0.038, 0.0205, 0.0158), (0.050, 0.0180, 0.0148)],
        col=c["Receiver"], material=m["ParkerizedSteel"], segments=64)
    port_cutters = [
        rounded_cutter("TMP_PPSh_EjectionPort", (0.058, 0.022, 0.012),
                       (-0.002, -0.019, 0.011), col=c["Receiver"], bevel_width=0.003),
        rounded_cutter("TMP_PPSh_MagazinePort", (0.052, 0.030, 0.016),
                       (0.012, 0.0, -0.019), col=c["Receiver"], bevel_width=0.003),
    ]
    apply_boolean(receiver, port_cutters, "PPSh_ReceiverOpenings")
    bevel(receiver, 0.0007, segments=2)

    bolt = cylinder("SM_PPSh_Bolt_Body", 0.0123, 0.108, (-0.067, 0, 0),
                    col=c["Internals"], material=m["BluedSteel"], axis="X", vertices=64)
    for idx, x in enumerate((-0.100, -0.065, -0.030), 1):
        torus(f"SM_PPSh_Bolt_Groove_{idx:02d}", 0.01245, 0.00065, (x, 0, 0),
              col=c["Internals"], material=m["DarkSteel"], axis="X", major_segments=48, minor_segments=8)
    bolt_handle = cylinder("SM_PPSh_BoltHandle_Stem", 0.0035, 0.018, (-0.055, -0.020, 0.008),
                           col=c["Controls"], material=m["BrightSteel"], axis="Y", vertices=32)
    bolt_knob = sphere("SM_PPSh_BoltHandle_Knob", 0.006, (-0.055, -0.031, 0.008),
                       col=c["Controls"], material=m["BluedSteel"])
    ctx.pivot("Bolt", [bolt], (-0.067, 0, 0))
    ctx.pivot("BoltHandle", [bolt_handle, bolt_knob], (-0.055, -0.018, 0.008))

    helix("SM_PPSh_RecoilSpring", (-0.100, 0, 0), 0.0137, 0.080, 9.0, 0.00085,
          axis="X", col=c["Internals"], material=m["BrightSteel"], steps=220)
    box("SM_PPSh_Ejector", (0.045, 0.003, 0.004), (0.013, -0.010, -0.003),
        col=c["Internals"], material=m["BrightSteel"], bevel_width=0.0004)

    # Magazine well: four separate walls leave a genuinely open feed channel.
    well_walls = [
        box("SM_PPSh_MagWell_Wall_L", (0.052, 0.003, 0.046), (0.012, -0.014, -0.038),
            col=c["Magazine"], material=m["ParkerizedSteel"], bevel_width=0.0006),
        box("SM_PPSh_MagWell_Wall_R", (0.052, 0.003, 0.046), (0.012, 0.014, -0.038),
            col=c["Magazine"], material=m["ParkerizedSteel"], bevel_width=0.0006),
        box("SM_PPSh_MagWell_Wall_F", (0.003, 0.028, 0.046), (0.035, 0, -0.038),
            col=c["Magazine"], material=m["ParkerizedSteel"], bevel_width=0.0006),
        box("SM_PPSh_MagWell_Wall_B", (0.003, 0.028, 0.046), (-0.011, 0, -0.038),
            col=c["Magazine"], material=m["ParkerizedSteel"], bevel_width=0.0006),
    ]
    for idx, wall in enumerate(well_walls, 1):
        wall["passage"] = f"magazine_well_wall_{idx}"

    tower_walls = [
        box("SM_PPSh_Drum_Tower_L", (0.028, 0.003, 0.043), (0.010, -0.0135, -0.052),
            col=c["Magazine"], material=m["ParkerizedSteel"], bevel_width=0.0005),
        box("SM_PPSh_Drum_Tower_R", (0.028, 0.003, 0.043), (0.010, 0.0135, -0.052),
            col=c["Magazine"], material=m["ParkerizedSteel"], bevel_width=0.0005),
        box("SM_PPSh_Drum_Tower_F", (0.003, 0.027, 0.043), (0.021, 0, -0.052),
            col=c["Magazine"], material=m["ParkerizedSteel"], bevel_width=0.0005),
        box("SM_PPSh_Drum_Tower_B", (0.003, 0.027, 0.043), (-0.001, 0, -0.052),
            col=c["Magazine"], material=m["ParkerizedSteel"], bevel_width=0.0005),
    ]
    for idx, wall in enumerate(tower_walls, 1):
        wall["passage"] = f"drum_feed_tower_wall_{idx}"

    drum = cylinder("SM_PPSh_Drum_Body", 0.064, 0.052, (0.010, 0, -0.086),
                    col=c["Magazine"], material=m["ParkerizedSteel"], axis="Y",
                    vertices=96, bevel_width=0.0018)
    for idx, y in enumerate((-0.027, 0.027), 1):
        torus(f"SM_PPSh_Drum_Rim_{idx:02d}", 0.056, 0.0016, (0.010, y, -0.086),
              col=c["Magazine"], material=m["BluedSteel"], axis="Y", major_segments=80, minor_segments=10)
    for idx in range(28):
        angle = 2 * math.pi * idx / 28
        x = 0.010 + 0.063 * math.cos(angle)
        z = -0.086 + 0.063 * math.sin(angle)
        cylinder(f"SM_PPSh_Drum_Flute_{idx + 1:02d}", 0.0016, 0.054, (x, 0, z),
                 col=c["Magazine"], material=m["DarkSteel"], axis="Y", vertices=12)
    spiral = curve_tube("SM_PPSh_Drum_SpiralGuide",
                        spiral_points((0.010, -0.0295, -0.086), 0.008, 0.049, 3.25, 280),
                        0.0012, col=c["Magazine"], material=m["Brass"])
    cylinder("SM_PPSh_Drum_Hub", 0.010, 0.005, (0.010, -0.0305, -0.086),
             col=c["Magazine"], material=m["BluedSteel"], axis="Y", vertices=48, bevel_width=0.0004)
    winding_key = box("SM_PPSh_Drum_WindingKey", (0.027, 0.004, 0.004),
                      (0.010, -0.034, -0.086), col=c["Controls"], material=m["BrightSteel"], bevel_width=0.0008)
    ctx.pivot("DrumMagazine", [drum, spiral, *tower_walls, winding_key], (0.010, 0, -0.038))
    magazine_catch = box("SM_PPSh_MagazineCatch_Lever", (0.026, 0.004, 0.006),
                         (0.043, -0.020, -0.048), col=c["Controls"], material=m["BluedSteel"], bevel_width=0.0008)
    ctx.pivot("MagazineCatch", [magazine_catch], (0.032, -0.020, -0.048))

    stock_profile = [
        (-0.574, 0.010), (-0.568, 0.020), (-0.545, 0.023), (-0.510, 0.018),
        (-0.470, 0.007), (-0.420, -0.002), (-0.360, -0.008), (-0.300, -0.011),
        (-0.240, -0.011), (-0.190, -0.008), (-0.170, 0.000),
        (-0.170, -0.030), (-0.205, -0.046), (-0.270, -0.056), (-0.340, -0.059),
        (-0.410, -0.058), (-0.470, -0.053), (-0.525, -0.050), (-0.574, -0.050),
    ]
    stock = profile_extrude("SM_PPSh_WoodenStock", stock_profile, 0.043,
                            col=c["Stock"], material=m["Wood"])
    bevel(stock, 0.0035, segments=4)
    set_smooth(stock, True)
    foregrip = profile_extrude(
        "SM_PPSh_ForeEnd",
        [(-0.170, -0.004), (0.050, -0.004), (0.050, -0.018),
         (0.000, -0.024), (-0.080, -0.030), (-0.170, -0.028)],
        0.041, col=c["Stock"], material=m["Wood"])
    bevel(foregrip, 0.0025, segments=3)
    set_smooth(foregrip, True)
    buttplate = box("SM_PPSh_Buttplate", (0.0045, 0.047, 0.076), (-0.575, 0, -0.014),
                    col=c["Stock"], material=m["BluedSteel"], bevel_width=0.0015)

    grip_panel = profile_extrude(
        "SM_PPSh_GripPanel_Right",
        [(-0.165, -0.010), (-0.110, -0.010), (-0.090, -0.027), (-0.095, -0.048),
         (-0.125, -0.062), (-0.165, -0.060)],
        0.004, col=c["Stock"], material=m["Bakelite"], location=(0, -0.022, 0))
    bevel(grip_panel, 0.001, segments=2)

    guard = oval_loop("SM_PPSh_TriggerGuard", (-0.095, 0, -0.040), 0.041, 0.020,
                      0.0022, col=c["Controls"], material=m["BluedSteel"])
    trigger = curve_tube("SM_PPSh_Trigger", [(-0.097, 0, -0.021), (-0.096, 0, -0.030),
                                            (-0.091, 0, -0.041), (-0.087, 0, -0.046)],
                         0.0018, col=c["Controls"], material=m["BrightSteel"])
    ctx.pivot("Trigger", [trigger], (-0.097, 0, -0.021))
    selector = box("SM_PPSh_SelectorLever", (0.017, 0.003, 0.004),
                   (-0.132, -0.020, -0.010), col=c["Controls"], material=m["BrightSteel"], bevel_width=0.0006)
    ctx.pivot("Selector", [selector], (-0.132, -0.020, -0.010))

    for idx, (x, y, z) in enumerate((
        (-0.150, -0.021, 0.002), (-0.115, -0.021, 0.005), (-0.075, -0.021, 0.005),
        (0.015, -0.021, 0.006), (0.034, -0.021, 0.002), (-0.555, -0.023, -0.014),
        (-0.285, -0.023, -0.030), (-0.195, -0.023, -0.020), (0.010, -0.029, -0.086),
    ), 1):
        for part in screw(f"SM_PPSh_Screw_{idx:02d}", (x, y, z), axis="Y",
                          col=c["Fasteners"], head=m["BrightSteel"], slot=m["DarkSteel"],
                          radius=0.0025, depth=0.0016):
            pass

    torus("SM_PPSh_SlingSwivel_Rear", 0.006, 0.0012, (-0.552, -0.024, -0.040),
          col=c["Fasteners"], material=m["BluedSteel"], axis="Y")
    torus("SM_PPSh_SlingSwivel_Front", 0.006, 0.0012, (0.066, -0.023, -0.014),
          col=c["Fasteners"], material=m["BluedSteel"], axis="Y")

    text_marking("SM_PPSh_Marking_Year", "1943", (-0.108, -0.0210, -0.004),
                 col=c["Markings"], material=m["Engraving"], size=0.0062)
    text_marking("SM_PPSh_Marking_Serial", "No.0417", (-0.045, -0.0210, -0.004),
                 col=c["Markings"], material=m["Engraving"], size=0.0052)
    text_marking("SM_PPSh_Marking_Caliber", "7.62", (0.020, -0.0210, -0.004),
                 col=c["Markings"], material=m["Engraving"], size=0.0050)


# -----------------------------------------------------------------------------
# Mosin-Nagant M1891/30, plain and PU-scoped
# -----------------------------------------------------------------------------

def build_mosin(ctx: Context, scoped: bool) -> None:
    m, c, slug = ctx.mats, ctx.cols, ctx.slug
    prefix = "SM_MosinPU" if scoped else "SM_Mosin"

    barrel = revolved_tube(
        f"{prefix}_Barrel_TrueBore",
        [(0.000, 0.0105, 0.0039), (0.065, 0.0090, 0.0039),
         (0.090, 0.0077, 0.0039), (0.650, 0.0070, 0.0039),
         (0.730, 0.0065, 0.0039)],
        col=c["Barrel"], material=m["BluedSteel"], segments=80)
    barrel["passage"] = "barrel_bore"
    revolved_tube(f"{prefix}_BoreShadow", [(-0.006, 0.0043, 0.0032), (-0.004, 0.0043, 0.0032)],
                  col=c["Internals"], material=m["BoreShadow"], segments=48)
    revolved_tube(f"{prefix}_MuzzleCrown",
                  [(0.727, 0.0070, 0.0039), (0.730, 0.0070, 0.0039)],
                  col=c["Barrel"], material=m["BrightSteel"], segments=64)
    revolved_tube(f"{prefix}_BoreLiner",
                  [(0.708, 0.00386, 0.00374), (0.730, 0.00386, 0.00374)],
                  col=c["Barrel"], material=m["BoreShadow"], segments=48)

    receiver = revolved_tube(
        f"{prefix}_Receiver_Shell",
        [(-0.076, 0.0166, 0.0118), (-0.066, 0.0175, 0.0118),
         (0.026, 0.0175, 0.0118), (0.048, 0.0148, 0.0105)],
        col=c["Receiver"], material=m["ParkerizedSteel"], segments=48)
    ejection = rounded_cutter(f"TMP_{prefix}_EjectionPort", (0.070, 0.024, 0.011),
                              (-0.018, -0.017, 0.010), col=c["Receiver"], bevel_width=0.0028)
    apply_boolean(receiver, [ejection], f"{prefix}_EjectionPort")
    bevel(receiver, 0.0006, segments=2)
    box(f"{prefix}_Receiver_TopFlat", (0.090, 0.020, 0.0035), (-0.018, 0, 0.0176),
        col=c["Receiver"], material=m["BluedSteel"], bevel_width=0.0005)

    bolt_body = cylinder(f"{prefix}_Bolt_Body", 0.0094, 0.098, (-0.035, 0, 0),
                         col=c["Internals"], material=m["BrightSteel"], axis="X", vertices=64)
    bolt_head = cylinder(f"{prefix}_Bolt_Head", 0.0102, 0.018, (0.020, 0, 0),
                         col=c["Internals"], material=m["BrightSteel"], axis="X", vertices=48)
    bolt_handle_parts = []
    if scoped:
        stem1 = cylinder(f"{prefix}_BoltHandle_Stem", 0.0032, 0.020, (-0.048, -0.017, 0.004),
                         col=c["Controls"], material=m["BluedSteel"], axis="Y", vertices=32)
        stem2 = cylinder(f"{prefix}_BoltHandle_Drop", 0.0032, 0.018, (-0.048, -0.028, -0.003),
                         col=c["Controls"], material=m["BluedSteel"], axis="Z", vertices=32)
        knob = sphere(f"{prefix}_BoltHandle_Knob", 0.0058, (-0.048, -0.028, -0.013),
                      col=c["Controls"], material=m["BluedSteel"])
        bolt_handle_parts = [stem1, stem2, knob]
    else:
        stem = cylinder(f"{prefix}_BoltHandle_Stem", 0.0032, 0.024, (-0.048, -0.024, 0.006),
                        col=c["Controls"], material=m["BrightSteel"], axis="Y", vertices=32)
        knob = sphere(f"{prefix}_BoltHandle_Knob", 0.006, (-0.048, -0.038, 0.006),
                      col=c["Controls"], material=m["BluedSteel"])
        bolt_handle_parts = [stem, knob]
    ctx.pivot("Bolt", [bolt_body, bolt_head], (-0.035, 0, 0))
    ctx.pivot("BoltHandle", bolt_handle_parts, (-0.048, -0.018, 0.006))

    # Internal magazine: open well, five visible cartridge silhouettes (art only).
    magazine_walls = [
        box(f"{prefix}_Magazine_Wall_L", (0.068, 0.003, 0.036), (-0.020, -0.013, -0.028),
            col=c["Magazine"], material=m["BluedSteel"], bevel_width=0.0005),
        box(f"{prefix}_Magazine_Wall_R", (0.068, 0.003, 0.036), (-0.020, 0.013, -0.028),
            col=c["Magazine"], material=m["BluedSteel"], bevel_width=0.0005),
        box(f"{prefix}_Magazine_Wall_F", (0.003, 0.026, 0.036), (0.011, 0, -0.028),
            col=c["Magazine"], material=m["BluedSteel"], bevel_width=0.0005),
        box(f"{prefix}_Magazine_Wall_B", (0.003, 0.026, 0.036), (-0.051, 0, -0.028),
            col=c["Magazine"], material=m["BluedSteel"], bevel_width=0.0005),
    ]
    for idx, wall in enumerate(magazine_walls, 1):
        wall["passage"] = f"magazine_well_wall_{idx}"
    for idx in range(5):
        cylinder(f"{prefix}_Cartridge_{idx + 1:02d}", 0.0034, 0.052,
                 (-0.018, -0.008 + idx * 0.004, -0.020 - (idx % 2) * 0.003),
                 col=c["Magazine"], material=m["Brass"], axis="X", vertices=20)

    guard = oval_loop(f"{prefix}_TriggerGuard", (-0.035, 0, -0.044), 0.044, 0.021,
                      0.0022, col=c["Controls"], material=m["BluedSteel"])
    trigger = curve_tube(f"{prefix}_Trigger", [(-0.032, 0, -0.021), (-0.031, 0, -0.032),
                                              (-0.026, 0, -0.044), (-0.022, 0, -0.049)],
                         0.0017, col=c["Controls"], material=m["BrightSteel"])
    ctx.pivot("Trigger", [trigger], (-0.032, 0, -0.021))

    stock_profile = [
        (-0.502, 0.008), (-0.496, 0.024), (-0.482, 0.030), (-0.455, 0.027),
        (-0.420, 0.016), (-0.370, 0.001), (-0.310, -0.009), (-0.245, -0.015),
        (-0.180, -0.018), (-0.105, -0.019), (-0.040, -0.020), (0.030, -0.019),
        (0.120, -0.016), (0.300, -0.015), (0.560, -0.014),
        (0.560, -0.030), (0.300, -0.038), (0.120, -0.045), (0.030, -0.050),
        (-0.040, -0.060), (-0.105, -0.066), (-0.180, -0.061), (-0.250, -0.056),
        (-0.320, -0.053), (-0.390, -0.052), (-0.455, -0.050), (-0.502, -0.045),
    ]
    stock = profile_extrude(f"{prefix}_WoodenStock", stock_profile, 0.046,
                            col=c["Stock"], material=m["Wood"])
    bevel(stock, 0.004, segments=4)
    set_smooth(stock, True)
    buttplate = box(f"{prefix}_Buttplate", (0.005, 0.049, 0.080), (-0.503, 0, -0.008),
                    col=c["Stock"], material=m["BluedSteel"], bevel_width=0.0015)
    for idx, y in enumerate((-0.011, 0.011), 1):
        box(f"{prefix}_Handguard_Side_{idx:02d}", (0.450, 0.006, 0.014),
            (0.325, y, 0.009), col=c["Stock"], material=m["Wood"], bevel_width=0.002)
    box(f"{prefix}_Handguard_Top", (0.450, 0.020, 0.004), (0.325, 0, 0.019),
        col=c["Stock"], material=m["Wood"], bevel_width=0.0015)

    for idx, x in enumerate((0.145, 0.520), 1):
        revolved_tube(f"{prefix}_BarrelBand_{idx:02d}",
                      [(x - 0.007, 0.0175, 0.0155), (x + 0.007, 0.0175, 0.0155)],
                      col=c["Barrel"], material=m["BluedSteel"], segments=64)
        for part in screw(f"{prefix}_BandScrew_{idx:02d}", (x, -0.018, -0.002), axis="Y",
                          col=c["Fasteners"], head=m["BrightSteel"], slot=m["DarkSteel"],
                          radius=0.0022, depth=0.0015):
            pass

    cylinder(f"{prefix}_CleaningRod", 0.0022, 0.590, (0.395, 0.011, -0.007),
             col=c["Barrel"], material=m["BrightSteel"], axis="X", vertices=24)
    cylinder(f"{prefix}_CleaningRod_Tip", 0.0030, 0.012, (0.692, 0.011, -0.007),
             col=c["Barrel"], material=m["Brass"], axis="X", vertices=24)

    rear_base = box(f"{prefix}_RearSight_Base", (0.080, 0.015, 0.004), (0.080, 0, 0.013),
                    col=c["Sights"], material=m["BluedSteel"], bevel_width=0.0006)
    rear_leaf = box(f"{prefix}_RearSight_Leaf", (0.070, 0.012, 0.002), (0.082, 0, 0.022),
                    col=c["Sights"], material=m["BrightSteel"], bevel_width=0.0004)
    box(f"{prefix}_FrontSight_Base", (0.016, 0.014, 0.004), (0.690, 0, 0.010),
        col=c["Sights"], material=m["BluedSteel"], bevel_width=0.0005)
    torus(f"{prefix}_FrontSight_Hood", 0.009, 0.0015, (0.690, 0, 0.018),
          col=c["Sights"], material=m["BluedSteel"], axis="X")
    box(f"{prefix}_FrontSight_Post", (0.003, 0.003, 0.011), (0.690, 0, 0.021),
        col=c["Sights"], material=m["BrightSteel"], bevel_width=0.0004)

    torus(f"{prefix}_SlingSwivel_Front", 0.006, 0.0012, (0.520, -0.025, -0.025),
          col=c["Fasteners"], material=m["BluedSteel"], axis="Y")
    torus(f"{prefix}_SlingSwivel_Rear", 0.006, 0.0012, (-0.400, -0.026, -0.030),
          col=c["Fasteners"], material=m["BluedSteel"], axis="Y")

    for idx, (x, y, z) in enumerate((
        (-0.065, -0.018, 0.003), (-0.030, -0.018, 0.004), (0.012, -0.018, 0.003),
        (-0.485, -0.024, -0.015), (-0.300, -0.024, -0.035), (-0.150, -0.024, -0.040),
        (0.145, -0.020, 0.010), (0.520, -0.020, 0.010),
    ), 1):
        for part in screw(f"{prefix}_Screw_{idx:02d}", (x, y, z), axis="Y",
                          col=c["Fasteners"], head=m["BrightSteel"], slot=m["DarkSteel"],
                          radius=0.0023, depth=0.0015):
            pass

    text_marking(f"{prefix}_Marking_Year", "1943", (-0.040, -0.0182, 0.000),
                 col=c["Markings"], material=m["Engraving"], size=0.0058)
    text_marking(f"{prefix}_Marking_Serial", "No.1738", (0.000, -0.0182, 0.000),
                 col=c["Markings"], material=m["Engraving"], size=0.0050)
    if not scoped:
        text_marking(f"{prefix}_Marking_Caliber", "7.62x54R", (0.040, -0.0182, -0.002),
                     col=c["Markings"], material=m["Engraving"], size=0.0042)

    if scoped:
        # PU scope: ~169 mm body, 3.5x, side-mounted above the left side of receiver.
        scope_y, scope_z = 0.042, 0.076
        scope = revolved_tube(
            f"{prefix}_PU_Scope_Body",
            [(-0.075, 0.0180, 0.0125), (-0.061, 0.0180, 0.0125),
             (-0.055, 0.0145, 0.0100), (0.060, 0.0145, 0.0100),
             (0.070, 0.0210, 0.0150), (0.094, 0.0210, 0.0150)],
            col=c["Optics"], material=m["BluedSteel"], segments=80,
            location=(0, scope_y, scope_z))
        scope["passage"] = "scope_optical_path"
        for idx, x in enumerate((-0.037, 0.045), 1):
            revolved_tube(f"{prefix}_PU_ScopeRing_{idx:02d}",
                          [(x - 0.007, 0.0190, 0.0147), (x + 0.007, 0.0190, 0.0147)],
                          col=c["Optics"], material=m["BluedSteel"], segments=64,
                          location=(0, scope_y, scope_z))
        # Objective and ocular lenses sit inside the open tube.
        cylinder(f"{prefix}_PU_ObjectiveLens", 0.0147, 0.0015, (0.091, scope_y, scope_z),
                 col=c["Optics"], material=m["Glass"], axis="X", vertices=64)
        cylinder(f"{prefix}_PU_OcularLens", 0.0122, 0.0015, (-0.073, scope_y, scope_z),
                 col=c["Optics"], material=m["Glass"], axis="X", vertices=64)
        for idx, x in enumerate((-0.050, 0.075), 1):
            torus(f"{prefix}_PU_LensRetainer_{idx:02d}", 0.0149, 0.0010,
                  (x, scope_y, scope_z), col=c["Optics"], material=m["BrightSteel"], axis="X")

        mount_base = box(f"{prefix}_PU_MountBase", (0.096, 0.007, 0.012),
                         (-0.022, 0.024, 0.018), col=c["Optics"],
                         material=m["ParkerizedSteel"], bevel_width=0.001)
        for idx, x in enumerate((-0.055, 0.012), 1):
            box(f"{prefix}_PU_MountPost_{idx:02d}", (0.008, 0.007, 0.045),
                (x, 0.026, 0.044), col=c["Optics"], material=m["ParkerizedSteel"],
                bevel_width=0.0008)
        box(f"{prefix}_PU_MountRail", (0.090, 0.008, 0.005),
            (-0.020, 0.040, 0.066), col=c["Optics"], material=m["BluedSteel"],
            bevel_width=0.0006)
        for idx, x in enumerate((-0.037, 0.045), 1):
            box(f"{prefix}_PU_RingSupport_{idx:02d}", (0.014, 0.008, 0.016),
                (x, 0.042, 0.068), col=c["Optics"], material=m["BluedSteel"],
                bevel_width=0.0006)
        for idx, (x, z) in enumerate(((-0.060, 0.030), (-0.030, 0.046), (0.005, 0.046), (0.020, 0.030)), 1):
            for part in screw(f"{prefix}_PU_MountScrew_{idx:02d}", (x, 0.028, z), axis="Y",
                              col=c["Fasteners"], head=m["BrightSteel"], slot=m["DarkSteel"],
                              radius=0.0022, depth=0.0015):
                pass

        elevation = cylinder(f"{prefix}_PU_ElevationTurret", 0.010, 0.012,
                             (0.006, scope_y, 0.093), col=c["Controls"],
                             material=m["BluedSteel"], axis="Z", vertices=48, bevel_width=0.0006)
        elevation_cap = cylinder(f"{prefix}_PU_ElevationCap", 0.011, 0.003,
                                 (0.006, scope_y, 0.100), col=c["Controls"],
                                 material=m["BrightSteel"], axis="Z", vertices=48)
        ctx.pivot("PU_ElevationTurret", [elevation, elevation_cap], (0.006, scope_y, 0.091))
        windage = cylinder(f"{prefix}_PU_WindageTurret", 0.0085, 0.010,
                           (0.006, 0.058, scope_z), col=c["Controls"],
                           material=m["BluedSteel"], axis="Y", vertices=48, bevel_width=0.0005)
        windage_cap = cylinder(f"{prefix}_PU_WindageCap", 0.0093, 0.003,
                               (0.006, 0.064, scope_z), col=c["Controls"],
                               material=m["BrightSteel"], axis="Y", vertices=48)
        ctx.pivot("PU_WindageTurret", [windage, windage_cap], (0.006, 0.056, scope_z))
        for idx in range(20):
            angle = 2 * math.pi * idx / 20
            bx = 0.006 + 0.0098 * math.cos(angle)
            by = scope_y + 0.0098 * math.sin(angle)
            box(f"{prefix}_PU_ElevationKnurl_{idx + 1:02d}", (0.0010, 0.0010, 0.010),
                (bx, by, 0.095), col=c["Optics"], material=m["DarkSteel"])
        text_marking(f"{prefix}_PU_ScopeMarking", "3.5x PU", (0.030, 0.0252, 0.076),
                     col=c["Markings"], material=m["Engraving"], size=0.0042)


def build_mosin_plain(ctx: Context) -> None:
    build_mosin(ctx, scoped=False)


def build_mosin_pu(ctx: Context) -> None:
    build_mosin(ctx, scoped=True)


# -----------------------------------------------------------------------------
# Nagant M1895
# -----------------------------------------------------------------------------

def build_nagant(ctx: Context) -> None:
    m, c = ctx.mats, ctx.cols
    prefix = "SM_Nagant"

    barrel = revolved_tube(
        f"{prefix}_Barrel_TrueBore",
        [(0.000, 0.0070, 0.0037), (0.018, 0.0066, 0.0037),
         (0.100, 0.0060, 0.0037), (0.114, 0.0058, 0.0037)],
        col=c["Barrel"], material=m["BluedSteel"], segments=80)
    barrel["passage"] = "barrel_bore"
    revolved_tube(f"{prefix}_BoreShadow", [(-0.005, 0.0040, 0.0031), (-0.003, 0.0040, 0.0031)],
                  col=c["Internals"], material=m["BoreShadow"], segments=48)
    revolved_tube(f"{prefix}_MuzzleCrown",
                  [(0.111, 0.0063, 0.0037), (0.114, 0.0063, 0.0037)],
                  col=c["Barrel"], material=m["BrightSteel"], segments=64)
    revolved_tube(f"{prefix}_BoreLiner",
                  [(0.096, 0.00366, 0.00355), (0.114, 0.00366, 0.00355)],
                  col=c["Barrel"], material=m["BoreShadow"], segments=48)

    box(f"{prefix}_BarrelRib", (0.100, 0.005, 0.0015), (0.060, 0, 0.0075),
        col=c["Barrel"], material=m["BluedSteel"], bevel_width=0.0004)
    box(f"{prefix}_FrontSight", (0.004, 0.0032, 0.008), (0.106, 0, 0.012),
        col=c["Sights"], material=m["BrightSteel"], bevel_width=0.0004)
    box(f"{prefix}_RearSight_Notch", (0.009, 0.004, 0.003), (-0.056, 0, 0.019),
        col=c["Sights"], material=m["BluedSteel"], bevel_width=0.0004)

    # Seven true chamber holes plus an open central arbor; top hole is on bore axis.
    cylinder_center_z = -0.012
    orbit = 0.012
    cylinder_obj = cylinder(f"{prefix}_Cylinder_7Chambers", 0.0205, 0.050,
                            (-0.023, 0, cylinder_center_z), col=c["Cylinder"],
                            material=m["BluedSteel"], axis="X", vertices=96)
    cylinder_obj["passage"] = "cylinder_chambers"
    cutters = []
    for idx in range(7):
        angle = math.pi / 2 + 2 * math.pi * idx / 7
        y = orbit * math.cos(angle)
        z = cylinder_center_z + orbit * math.sin(angle)
        cutters.append(cylinder(f"TMP_{prefix}_Chamber_{idx + 1:02d}", 0.0040, 0.060,
                                (-0.023, y, z), col=c["Cylinder"], material=None,
                                axis="X", vertices=32))
    apply_boolean(cylinder_obj, cutters, f"{prefix}_CylinderChambers")
    bevel(cylinder_obj, 0.00035, segments=2)
    # Exterior flutes are separate decorative half-rounds; keeping them out of
    # the Boolean keeps the seven chamber passages robust and auditable.
    for idx in range(7):
        angle = math.pi / 2 + 2 * math.pi * idx / 7
        fy = 0.0203 * math.cos(angle)
        fz = cylinder_center_z + 0.0203 * math.sin(angle)
        cylinder(f"{prefix}_Cylinder_Flute_{idx + 1:02d}", 0.0033, 0.048,
                 (-0.023, fy, fz), col=c["Cylinder"], material=m["DarkSteel"],
                 axis="X", vertices=20)
    cylinder(f"{prefix}_Cylinder_Arbor", 0.0028, 0.062, (-0.023, 0, cylinder_center_z),
             col=c["Internals"], material=m["BrightSteel"], axis="X", vertices=32)
    for idx in range(7):
        angle = math.pi / 2 + 2 * math.pi * idx / 7
        y = orbit * math.cos(angle)
        z = cylinder_center_z + orbit * math.sin(angle)
        torus(f"{prefix}_ChamberRim_{idx + 1:02d}", 0.0041, 0.0005,
              (-0.0485, y, z), col=c["Cylinder"], material=m["Brass"], axis="X",
              major_segments=32, minor_segments=8)
    ctx.pivot("Cylinder", [cylinder_obj], (-0.023, 0, cylinder_center_z))

    # Frame side plates with a large cylinder window.
    frame_profile = [
        (-0.121, 0.014), (-0.105, 0.021), (-0.075, 0.021), (-0.060, 0.016),
        (-0.050, 0.008), (-0.045, -0.015), (-0.030, -0.041), (-0.012, -0.050),
        (0.006, -0.047), (0.008, 0.004), (-0.010, 0.020), (-0.045, 0.023),
        (-0.075, 0.030), (-0.095, 0.030), (-0.121, 0.022),
    ]
    for idx, y in enumerate((-0.019, 0.019), 1):
        plate = profile_extrude(f"{prefix}_Frame_SidePlate_{idx:02d}", frame_profile, 0.003,
                                 col=c["Receiver"], material=m["ParkerizedSteel"],
                                 location=(0, y, 0))
        window = cylinder(f"TMP_{prefix}_FrameWindow_{idx:02d}", 0.0218, 0.012,
                          (-0.023, y, cylinder_center_z), col=c["Receiver"],
                          material=None, axis="Y", vertices=64)
        apply_boolean(plate, [window], f"{prefix}_FrameWindow_{idx:02d}")
        bevel(plate, 0.0007, segments=2)
    box(f"{prefix}_TopStrap", (0.055, 0.040, 0.004), (-0.045, 0, 0.020),
        col=c["Receiver"], material=m["ParkerizedSteel"], bevel_width=0.0008)
    box(f"{prefix}_BottomFrame", (0.065, 0.040, 0.005), (-0.025, 0, -0.046),
        col=c["Receiver"], material=m["ParkerizedSteel"], bevel_width=0.0008)

    loading_gate = profile_extrude(
        f"{prefix}_LoadingGate",
        [(-0.018, -0.008), (0.006, -0.008), (0.006, 0.007), (-0.018, 0.007)],
        0.003, col=c["Controls"], material=m["BluedSteel"], location=(0, -0.022, 0))
    bevel(loading_gate, 0.0008, segments=3)
    ctx.pivot("LoadingGate", [loading_gate], (-0.018, -0.022, 0.000))

    hammer = profile_extrude(
        f"{prefix}_Hammer",
        [(-0.090, 0.018), (-0.078, 0.030), (-0.064, 0.028), (-0.060, 0.020),
         (-0.068, 0.016), (-0.074, 0.008), (-0.082, 0.005), (-0.090, 0.008)],
        0.008, col=c["Controls"], material=m["BluedSteel"])
    bevel(hammer, 0.0008, segments=3)
    ctx.pivot("Hammer", [hammer], (-0.080, 0, 0.012))

    guard = oval_loop(f"{prefix}_TriggerGuard", (-0.055, 0, -0.042), 0.032, 0.019,
                      0.0022, col=c["Controls"], material=m["BluedSteel"])
    trigger = curve_tube(f"{prefix}_Trigger", [(-0.055, 0, -0.025), (-0.053, 0, -0.035),
                                               (-0.049, 0, -0.045), (-0.044, 0, -0.049)],
                         0.0018, col=c["Controls"], material=m["BrightSteel"])
    ctx.pivot("Trigger", [trigger], (-0.055, 0, -0.025))

    grip_profile = [
        (-0.118, 0.003), (-0.106, 0.008), (-0.086, -0.004), (-0.070, -0.024),
        (-0.066, -0.050), (-0.075, -0.080), (-0.092, -0.109), (-0.110, -0.124),
        (-0.121, -0.121), (-0.121, -0.094), (-0.115, -0.060), (-0.118, -0.025),
    ]
    for idx, y in enumerate((-0.022, 0.022), 1):
        grip = profile_extrude(f"{prefix}_CheckeredGrip_{idx:02d}", grip_profile, 0.004,
                                col=c["Stock"], material=m["CheckeredGrip"], location=(0, y, 0))
        bevel(grip, 0.0015, segments=3)
        set_smooth(grip, True)
    for idx, y in enumerate((-0.023, 0.023), 1):
        for part in screw(f"{prefix}_GripScrew_{idx:02d}", (-0.100, y, -0.055), axis="Y",
                          col=c["Fasteners"], head=m["BrightSteel"], slot=m["DarkSteel"],
                          radius=0.0024, depth=0.0015):
            pass
    torus(f"{prefix}_LanyardRing", 0.006, 0.0012, (-0.116, 0, -0.120),
          col=c["Fasteners"], material=m["BluedSteel"], axis="Y")

    # Ejector rod assembly on the left side.
    cylinder(f"{prefix}_EjectorHousing", 0.0042, 0.024, (0.011, 0.012, -0.012),
             col=c["Barrel"], material=m["ParkerizedSteel"], axis="X", vertices=32)
    cylinder(f"{prefix}_EjectorRod", 0.0021, 0.072, (0.043, 0.012, -0.012),
             col=c["Barrel"], material=m["BrightSteel"], axis="X", vertices=24)
    ejector_head = cylinder(f"{prefix}_EjectorHead", 0.0038, 0.012, (0.081, 0.012, -0.012),
                            col=c["Controls"], material=m["BluedSteel"], axis="X",
                            vertices=32, bevel_width=0.0004)
    ctx.pivot("EjectorRod", [ejector_head], (0.075, 0.012, -0.012))

    for idx, (x, y, z) in enumerate((
        (-0.108, -0.021, 0.014), (-0.060, -0.021, 0.016), (-0.030, -0.021, -0.037),
        (-0.095, -0.023, -0.030), (-0.115, -0.023, -0.100),
    ), 1):
        for part in screw(f"{prefix}_Screw_{idx:02d}", (x, y, z), axis="Y",
                          col=c["Fasteners"], head=m["BrightSteel"], slot=m["DarkSteel"],
                          radius=0.0020, depth=0.0014):
            pass

    text_marking(f"{prefix}_Marking_Year", "1941", (-0.090, -0.0208, 0.006),
                 col=c["Markings"], material=m["Engraving"], size=0.0042)
    text_marking(f"{prefix}_Marking_Serial", "No.2385", (-0.070, -0.0208, -0.011),
                 col=c["Markings"], material=m["Engraving"], size=0.0036)


# -----------------------------------------------------------------------------
# Build pipeline
# -----------------------------------------------------------------------------

BUILDERS: dict[str, Callable[[Context], None]] = {
    "ppsh-41": build_ppsh,
    "mosin-m91-30": build_mosin_plain,
    "mosin-m91-30-pu": build_mosin_pu,
    "nagant-m1895": build_nagant,
}


def create_controls(ctx: Context, factor: float) -> list[str]:
    names = []
    for entry in ctx.pivots:
        pivot = tuple(float(v) * factor for v in entry["pivot"])
        empty = control_group(entry["objects"], pivot, entry["name"], ctx.col("Controls"))
        names.append(empty.name)
    return names


def build_asset(slug: str) -> dict:
    scene = reset_scene(slug)
    ctx = make_context(slug)
    BUILDERS[slug](ctx)
    meshes = model_meshes([ctx.root])
    factor = normalize_length(meshes, TARGET_LENGTHS[slug])
    smart_uv_all(meshes)
    control_names = create_controls(ctx, factor)
    all_model_objects = model_meshes([ctx.root])
    low, high = world_bbox(all_model_objects, evaluated=True)
    create_studio(slug, low, high)

    scene["asset_slug"] = slug
    scene["asset_variant"] = VARIANTS[slug]
    scene["axis_convention"] = "muzzle +X; up +Z; right side -Y; world origin at bore axis / breech face"
    scene["unit_system"] = "metric; 1 Blender unit = 1 m"
    scene["model_collection"] = ctx.root.name
    scene["source_generator"] = "scripts/build_wwii_arms.py"
    scene["target_length_mm"] = round(TARGET_LENGTHS[slug] * 1000.0, 3)
    scene["normalization_factor"] = factor

    texture_files = sorted(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ASSETS / slug / "textures").glob("*.png")
    )
    collection_stats = []
    for col in [ctx.root, *ctx.root.children]:
        objs = [obj for obj in col.all_objects if obj.type == "MESH"]
        if not objs:
            continue
        collection_stats.append({"name": col.name, "objects": len(objs)})
    stats = {
        "slug": slug,
        "variant": VARIANTS[slug],
        "source_file": f"assets/{slug}/source/{slug}.blend",
        "blender_version": bpy.app.version_string,
        "render_engine": scene.render.engine,
        "unit_scale_length": 1.0,
        "up_axis": "Z",
        "muzzle_axis": "+X",
        "right_side": "-Y",
        "target_length_mm": round(TARGET_LENGTHS[slug] * 1000.0, 3),
        "normalization_factor": round(factor, 8),
        "bbox_mm": [round(float(v) * 1000.0, 3) for v in (high - low)],
        "bbox_min_mm": [round(float(v) * 1000.0, 3) for v in low],
        "bbox_max_mm": [round(float(v) * 1000.0, 3) for v in high],
        "triangle_count": triangle_count(all_model_objects),
        "object_count": len(all_model_objects),
        "materials": sorted(mat.name for mat in bpy.data.materials if mat.name.startswith(f"M_{slug}_")),
        "texture_files": texture_files,
        "textures_count": len(texture_files),
        "uv_layer": "UVMap",
        "pivot_controls": control_names,
        "collections": collection_stats,
        "animation": "none",
        "game_ready": False,
        "notes": "Visual art asset; geometric passages are for inspection only, not manufacturing dimensions.",
    }
    blend_path = save_blend(slug, stats)
    print(f"BUILD {slug}: {stats['object_count']} objects, {stats['triangle_count']} tris, "
          f"bbox {stats['bbox_mm']} mm, {blend_path.stat().st_size / 1024:.0f} KiB, {blend_path}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=(*SLUGS, "all"), default="all")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    slugs = SLUGS if args.only == "all" else (args.only,)
    results = {slug: build_asset(slug) for slug in slugs}
    if args.output_json:
        import json
        Path(args.output_json).write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
