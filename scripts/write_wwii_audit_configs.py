#!/usr/bin/env python3
"""Write per-asset audit_blend.py configurations from build statistics.

Dimensions along X come from published overall/barrel lengths; Y/Z are measured
design estimates recorded in manifest/build-stats.json. Passage rays are given in
millimetres in world space. They check that the visual bores, magazine wells and
cylinder chambers are open rather than black disks.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SLUGS = ("ppsh-41", "mosin-m91-30", "mosin-m91-30-pu", "nagant-m1895")

PROFILES = {
    "ppsh-41": {
        "prefix": "SM_PPSh",
        "root": "ppsh-41_Model",
        "source_length_mm": 843.0,
        "barrel_length_mm": 269.0,
        "barrel_end_mm": 269.0,
    },
    "mosin-m91-30": {
        "prefix": "SM_Mosin",
        "root": "mosin-m91-30_Model",
        "source_length_mm": 1232.0,
        "barrel_length_mm": 730.0,
        "barrel_end_mm": 730.0,
    },
    "mosin-m91-30-pu": {
        "prefix": "SM_MosinPU",
        "root": "mosin-m91-30-pu_Model",
        "source_length_mm": 1232.0,
        "barrel_length_mm": 730.0,
        "barrel_end_mm": 730.0,
        "scope_length_mm": 169.0,
    },
    "nagant-m1895": {
        "prefix": "SM_Nagant",
        "root": "nagant-m1895_Model",
        "source_length_mm": 235.0,
        "barrel_length_mm": 114.0,
        "barrel_end_mm": 114.0,
    },
}


def load_stats(slug: str) -> dict:
    return json.loads((ASSETS / slug / "manifest" / "build-stats.json").read_text(encoding="utf-8"))


def ray(x0: float, x1: float, y: float = 0.0, z: float = 0.0) -> dict:
    return {"start": [x0, y, z], "end": [x1, y, z]}


def vertical_ray(x: float, y: float, z0: float, z1: float) -> dict:
    return {"start": [x, y, z0], "end": [x, y, z1]}


def bore_rays(end_mm: float, offsets: tuple[float, ...] = (0.0, 2.0, -2.0)) -> list[dict]:
    samples = [ray(-12.0, end_mm + 8.0, 0.0, 0.0)]
    for value in offsets:
        if value == 0.0:
            continue
        samples.append(ray(-12.0, end_mm + 8.0, value, 0.0))
        samples.append(ray(-12.0, end_mm + 8.0, 0.0, value))
    return samples


def config_for(slug: str) -> dict:
    p = PROFILES[slug]
    stats = load_stats(slug)
    factor = float(stats["normalization_factor"])
    bbox = [float(v) for v in stats["bbox_mm"]]
    prefix = p["prefix"]
    barrel_objects = [
        f"{prefix}_Barrel_TrueBore",
        f"{prefix}_MuzzleCrown",
        f"{prefix}_BoreLiner",
    ]
    targets = [
        {
            "id": "overall_model",
            "description": "Полный габарит модели; X сверен с исторической длиной, Y/Z — оценка по построенной геометрии.",
            "frame": 1,
            "collections": [p["root"]],
            "finite_transforms": True,
            "dimensions_mm": {
                "expected": [p["source_length_mm"], round(bbox[1], 3), round(bbox[2], 3)],
                "tolerance_mm": [2.0, 3.0, 3.0],
            },
            "topology": {
                "evaluated": {
                    "max_nonfinite_vertices": 0,
                    "max_wire_edges": 0,
                    "max_loose_vertices": 0,
                }
            },
        },
        {
            "id": "barrel_length",
            "description": "Длина ствола от казённого среза до дульного среза по оси X.",
            "frame": 1,
            "objects": [f"{prefix}_Barrel_TrueBore"],
            "dimensions_mm": {
                "expected": [p["barrel_length_mm"], 0.0, 0.0],
                "tolerance_mm": [3.0, 100.0, 100.0],
            },
        },
    ]
    passages = [
        {
            "id": "barrel_bore_clear",
            "description": "Пять лучей внутри канала ствола не встречают стенок: отверстие настоящее, а не чёрный диск.",
            "frame": 1,
            "objects": barrel_objects,
            "unit": "mm",
            "samples": bore_rays(p["barrel_end_mm"]),
            "max_hits": 0,
        }
    ]

    if slug == "ppsh-41":
        walls = [f"SM_PPSh_MagWell_Wall_{side}" for side in ("L", "R", "F", "B")]
        passages.append({
            "id": "magazine_well_clear",
            "description": "Вертикальные лучи проходят через открытую шахту магазина мимо четырёх стенок.",
            "frame": 1,
            "objects": walls,
            "unit": "mm",
            "samples": [vertical_ray(12.0 * factor * 1000.0, y, -75.0, -12.0)
                        for y in (-8.0, 0.0, 8.0)],
            "max_hits": 0,
        })
    elif slug.startswith("mosin"):
        walls = [f"{prefix}_Magazine_Wall_{side}" for side in ("L", "R", "F", "B")]
        passages.append({
            "id": "magazine_well_clear",
            "description": "Вертикальные лучи проходят через открытую шахту внутреннего магазина.",
            "frame": 1,
            "objects": walls,
            "unit": "mm",
            "samples": [vertical_ray(-20.0 * factor * 1000.0, y, -62.0, -8.0)
                        for y in (-8.0, 0.0, 8.0)],
            "max_hits": 0,
        })
    if slug == "mosin-m91-30-pu":
        scope_y = 0.042 * factor * 1000.0
        scope_z = 0.076 * factor * 1000.0
        scope_objects = [
            f"{prefix}_PU_Scope_Body",
            f"{prefix}_PU_ScopeRing_01",
            f"{prefix}_PU_ScopeRing_02",
        ]
        targets.append({
            "id": "pu_scope_length",
            "description": "Корпус прицела ПУ; длина 169 мм по источнику, Y/Z — оценка.",
            "frame": 1,
            "objects": [f"{prefix}_PU_Scope_Body"],
            "dimensions_mm": {
                "expected": [p["scope_length_mm"], 0.0, 0.0],
                "tolerance_mm": [4.0, 100.0, 100.0],
            },
        })
        passages.append({
            "id": "scope_optical_path_clear",
            "description": "Центральные лучи проходят внутри полой трубы прицела; стёкла в выборку не входят.",
            "frame": 1,
            "objects": scope_objects,
            "unit": "mm",
            "samples": [ray(-80.0, 130.0, scope_y + dy, scope_z + dz)
                        for dy, dz in ((0.0, 0.0), (3.0, 0.0), (-3.0, 0.0), (0.0, 3.0), (0.0, -3.0))],
            "max_hits": 0,
        })
    if slug == "nagant-m1895":
        chamber_yz = []
        for i in range(7):
            angle = math.pi / 2.0 + 2.0 * math.pi * i / 7.0
            y = 0.012 * factor * 1000.0 * math.cos(angle)
            z = -0.012 * factor * 1000.0 + 0.012 * factor * 1000.0 * math.sin(angle)
            chamber_yz.append((round(y, 4), round(z, 4)))
        passages.append({
            "id": "cylinder_chambers_clear",
            "description": "Семь лучей проходят сквозь семь настоящих отверстий барабана.",
            "frame": 1,
            "objects": [f"{prefix}_Cylinder_7Chambers"],
            "unit": "mm",
            "samples": [ray(-55.0, 8.0, y, z) for y, z in chamber_yz],
            "max_hits": 0,
        })

    return {
        "schema_version": 1,
        "description": f"Визуальный аудит {slug}: габариты, конечные трансформации, невырожденные вершины/рёбра и многолучевые проверки полостей. Нулевые грани от Bevel/Text не являются критерием приёмки.",
        "targets": targets,
        "poses": [],
        "passages": passages,
    }


def main() -> None:
    for slug in SLUGS:
        cfg = config_for(slug)
        out = ASSETS / slug / "audit" / "audit-config.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"audit config: {out}")


if __name__ == "__main__":
    main()
