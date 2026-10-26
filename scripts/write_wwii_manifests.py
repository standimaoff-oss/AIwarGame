#!/usr/bin/env python3
"""Create schema-v2 manifests from build stats, proof indexes and audit reports."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SLUGS = ("ppsh-41", "mosin-m91-30", "mosin-m91-30-pu", "nagant-m1895")
BRANCH = "arena/64d1db80-aiwargame"

NAMES = {
    "ppsh-41": "ППШ-41 с барабанным магазином",
    "mosin-m91-30": "Винтовка Мосина обр. 1891/30, механический прицел",
    "mosin-m91-30-pu": "Винтовка Мосина обр. 1891/30 с оптическим прицелом ПУ",
    "nagant-m1895": "Револьвер Нагана обр. 1895",
}

SOURCE_NOTES = {
    "ppsh-41": [
        "Длина 843 мм и ствол 269 мм: Wikipedia и MuseumOfWeapon.",
        "Выбран 71-зарядный барабанный магазин и поздний деревянный приклад.",
    ],
    "mosin-m91-30": [
        "Длина 1232 мм и ствол 730 мм: Wikipedia и Sniper Central.",
        "Рядовая пехотная комплектация с механическими прицельными приспособлениями.",
    ],
    "mosin-m91-30-pu": [
        "Длина 1232 мм и ствол 730 мм: Wikipedia и Sniper Central.",
        "Прицел ПУ 3,5× длиной около 169 мм: Russian Mosin Nagant и Guns & Ammo.",
    ],
    "nagant-m1895": [
        "Длина 235 мм и ствол 114 мм: Wikipedia; Modern Firearms даёт 230/114 мм.",
        "Выбран 7-зарядный барабан и тёмные щёчки рукояти.",
    ],
}

PROVENANCE = [
    {
        "source": "Wikipedia — PPSh-41",
        "url": "https://en.wikipedia.org/wiki/PPSh-41",
        "license": "CC BY-SA",
        "used_for": "габариты ППШ-41, калибр и тип магазинов",
    },
    {
        "source": "MuseumOfWeapon — PPSh-41",
        "url": "https://sites.google.com/view/museumofweapon/collections/submachine-guns/ppsh-41-eng",
        "license": "визуально-справочный источник",
        "used_for": "независимое подтверждение 843/269 мм",
    },
    {
        "source": "Wikipedia — Mosin–Nagant",
        "url": "https://en.wikipedia.org/wiki/Mosin%E2%80%93Nagant",
        "license": "CC BY-SA",
        "used_for": "длина M91/30, ствол 730 мм, вариант с ПУ 3,5×",
    },
    {
        "source": "Sniper Central — M1891/30 Sniper",
        "url": "https://snipercentral.com/mosin-nagant-189130-sniper/",
        "license": "визуально-справочный источник",
        "used_for": "подтверждение 1232 мм / 729 мм и снайперской комплектации",
    },
    {
        "source": "Russian Mosin Nagant — PU scope",
        "url": "https://boydhouse.com/darryl/russianmosinnagant/sniper_section.html",
        "license": "визуально-справочный источник",
        "used_for": "длина прицела ПУ около 169 мм",
    },
    {
        "source": "Guns & Ammo — PU scope diameter",
        "url": "https://www.gunsandammo.com/editorial/best-world-war-ii-sniper-rifle-3-mosin-nagant/527411",
        "license": "визуально-справочный источник",
        "used_for": "диаметр и кратность прицела ПУ",
    },
    {
        "source": "Wikipedia — Nagant M1895",
        "url": "https://en.wikipedia.org/wiki/Nagant_M1895",
        "license": "CC BY-SA",
        "used_for": "длина 235 мм, ствол 114 мм, 7-зарядный барабан",
    },
    {
        "source": "Modern Firearms — Nagant m.1895",
        "url": "https://modernfirearms.net/en/handguns/double-action-revolvers/russia-double-action-revolvers/nagan-obr-1895-eng/",
        "license": "визуально-справочный источник",
        "used_for": "независимое подтверждение длины и ёмкости барабана",
    },
]

MAP_NAMES = {"BaseColor", "Roughness", "Metallic", "Normal", "AO"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def texture_entries(slug: str) -> list[dict]:
    entries = []
    for path in sorted((ASSETS / slug / "textures").glob("T_*.png")):
        stem = path.stem
        parts = stem.split("_")
        map_name = next((p for p in parts if p in MAP_NAMES), "Other")
        set_name = next((p for p in parts if p in {
            "BluedSteel", "ParkerizedSteel", "Wood", "Bakelite", "Brass", "Glass"}), "Default")
        entries.append({
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "map": map_name,
            "set": set_name,
            "width": 1024,
            "height": 1024,
            "colorspace": "sRGB" if map_name == "BaseColor" else "Non-Color",
            "packed": False,
            "tilable": True,
            "provenance": "оригинальная процедурная генерация scripts/generate_wwii_textures.py",
        })
    return entries


def proof_entries(slug: str, index: dict) -> list[dict]:
    labels = {
        "hero": ("общий вид, пропорции и материалы", "hero"),
        "right": ("правый ортографический силуэт", "silhouette"),
        "left": ("левый ортографический силуэт", "silhouette"),
        "top": ("вид сверху и симметрия", "silhouette"),
        "muzzle": ("дульный срез и переднее прицельное приспособление", "macro"),
        "macro_bore": ("настоящий сквозной канал ствола и внутренняя стенка", "macro"),
        "clay": ("clay-проходка формы без влияния текстур", "clay"),
        "turntable": ("круговой осмотр со всех сторон", "turntable"),
    }
    proofs = []
    for key, path in index.get("proofs", {}).items():
        criterion, kind = labels.get(key, ("дополнительное доказательство", "other"))
        proofs.append({
            "path": path,
            "criterion": criterion,
            "kind": kind,
            "engine": "CYCLES",
        })
    return proofs


def audit_block(slug: str) -> dict:
    report_path = ASSETS / slug / "audit" / "audit-report.json"
    data = read_json(report_path)
    checks = data.get("checks", [])
    failed = sum(1 for c in checks if c.get("status") == "FAIL")
    return {
        "config": f"assets/{slug}/audit/audit-config.json",
        "report": f"assets/{slug}/audit/audit-report.json",
        "status": data.get("status", "not_run"),
        "checks_total": len(checks),
        "checks_failed": failed,
    }


def manifest_for(slug: str) -> dict:
    stats = read_json(ASSETS / slug / "manifest" / "build-stats.json")
    proof_index = read_json(ASSETS / slug / "renders" / "proofs-index.json")
    textures = texture_entries(slug)
    materials = [{"name": name, "procedural": not any(
        token in name for token in ("BluedSteel", "ParkerizedSteel", "Wood", "Bakelite", "Brass", "Glass")
    )} for name in stats.get("materials", [])]
    open_items = [
        "Game-ready оптимизация, LOD, collision и экспорт в движок не заказаны и не выполнялись.",
        "Риг и анимация не заказаны; для подвижных деталей созданы только pivot-контролы.",
        "Текстуры 1K процедурные; внешние HDRI и чужие 3D-модели не импортировались.",
        "Габариты по осям Y/Z и мелкие детали — визуальная оценка, а не обмер конкретного музейного экземпляра.",
        "Маркировки вымышленные; модель не является чертежом или производственной документацией.",
    ]
    open_items.extend(SOURCE_NOTES[slug])
    return {
        "schema_version": 2,
        "generated_by": "scripts/write_wwii_manifests.py + manifest/build-stats.json",
        "source_file": stats["source_file"],
        "identity": {
            "slug": slug,
            "name": NAMES[slug],
            "archetype": "hard_surface",
            "variant": stats["variant"],
            "version": "v001_procedural",
            "status": "review",
            "branch": BRANCH,
        },
        "units": {
            "unit": "m",
            "scale_length": 1.0,
            "up_axis": "Z",
            "export_up_axis": "Y",
            "unit_system": "metric",
        },
        "dimensions_mm": {
            "bbox": stats["bbox_mm"],
            "frame": 1,
            "includes": "все видимые детали модели, включая прицел/магазин; студийный пол, камеры и света исключены",
            "scope": f"collection: {slug}_Model",
            "axis_convention": "дуло +X, верх +Z, правая сторона −Y, начало координат на оси канала у казённого среза",
        },
        "budget": {
            "triangles": stats["triangle_count"],
            "triangles_limit": 120000,
            "vertices": None,
            "objects": stats["object_count"],
            "material_sets": 6,
            "texture_resolution": "1K",
            "lods": 0,
            "udim_tiles": 0,
        },
        "collections": stats.get("collections", []),
        "materials": materials,
        "textures": textures,
        "rig": {
            "type": "pivots",
            "controls": stats.get("pivot_controls", []),
            "frame_start": 1,
            "frame_end": 1,
            "animation_kind": "none",
            "notes": "подвижные детали имеют empties-контролы с реальными pivot-точками; анимации нет",
        },
        "exports": [],
        "proofs": proof_entries(slug, proof_index),
        "audit": audit_block(slug),
        "provenance": PROVENANCE,
        "open_items": open_items,
    }


def main() -> None:
    for slug in SLUGS:
        data = manifest_for(slug)
        out = ASSETS / slug / "manifest" / "asset-manifest.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"manifest: {out} ({len(data['textures'])} textures, {len(data['proofs'])} proofs, audit {data['audit']['status']})")


if __name__ == "__main__":
    main()
