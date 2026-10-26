#!/usr/bin/env python3
"""glTF/GLB inspector. Standalone Python 3.9+, no third-party packages.

    python gltf_report.py <file.glb|file.gltf>... [--check] [--json out.json]
                          [--max-triangles N]

Parses the JSON document (and the JSON chunk of a binary .glb), then reports
structure, triangle and vertex counts, material values, textures, extensions
and the problems that usually break engine imports: missing external files,
required compression extensions, normals without tangents, unit scale hints.
Read-only. Exit code 0 = ok, 1 = check failures, 2 = bad input.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys

TOOL_VERSION = "1.0.0"
COMPRESSION_EXTENSIONS = (
    "KHR_draco_mesh_compression", "EXT_meshopt_compression",
    "KHR_texture_basisu", "EXT_texture_webp",
)


def load_document(path):
    """Return (document, glb_info) or raise ValueError."""
    with open(path, "rb") as handle:
        head = handle.read(20)
        if head[:4] == b"glTF":
            if len(head) < 12:
                raise ValueError("truncated GLB header")
            version, total = struct.unpack("<II", head[4:12])
            chunk_len, chunk_type = struct.unpack("<II", head[12:20])
            if chunk_type != 0x4E4F534A:
                raise ValueError("first GLB chunk is not JSON")
            payload = handle.read(chunk_len)
            if len(payload) < chunk_len:
                raise ValueError("truncated GLB JSON chunk")
            document = json.loads(payload.decode("utf-8"))
            binary_len = 0
            rest = handle.read(8)
            if len(rest) == 8:
                bin_len, bin_type = struct.unpack("<II", rest)
                if bin_type == 0x004E4942:
                    binary_len = bin_len
            return document, {"container": "glb", "glb_version": version,
                              "declared_length": total, "json_chunk": chunk_len,
                              "binary_chunk": binary_len}
        handle.seek(0)
        text = handle.read()
    try:
        document = json.loads(text.decode("utf-8"))
    except ValueError as exc:
        raise ValueError("not valid JSON: %s" % exc)
    return document, {"container": "gltf", "declared_length": len(text)}


def accessor_count(document, index):
    accessors = document.get("accessors") or []
    if not isinstance(index, int) or index < 0 or index >= len(accessors):
        return 0
    return int(accessors[index].get("count") or 0)


def has_accessor(document, index):
    accessors = document.get("accessors") or []
    return isinstance(index, int) and 0 <= index < len(accessors)


def analyse(path, args):
    entry = {
        "path": path.replace(os.sep, "/"),
        "bytes": os.path.getsize(path),
        "errors": [],
        "warnings": [],
        "info": [],
    }
    try:
        document, container = load_document(path)
    except (OSError, ValueError) as exc:
        entry["errors"].append("cannot read glTF: %s" % exc)
        return entry
    entry["container"] = container
    base_dir = os.path.dirname(os.path.abspath(path))

    def error(message):
        entry["errors"].append(message)

    def warn(message):
        entry["warnings"].append(message)

    def note(message):
        entry["info"].append(message)

    asset = document.get("asset") or {}
    version = str(asset.get("version") or "")
    entry["glTF_version"] = version
    entry["generator"] = asset.get("generator")
    if not version.startswith("2"):
        error("asset.version is '%s'; glTF 2.0 expected" % version)

    scenes = document.get("scenes") or []
    nodes = document.get("nodes") or []
    meshes = document.get("meshes") or []
    materials = document.get("materials") or []
    textures = document.get("textures") or []
    images = document.get("images") or []
    animations = document.get("animations") or []
    skins = document.get("skins") or []
    accessors = document.get("accessors") or []
    buffers = document.get("buffers") or []
    buffer_views = document.get("bufferViews") or []

    entry["counts"] = {
        "scenes": len(scenes), "nodes": len(nodes), "meshes": len(meshes),
        "materials": len(materials), "textures": len(textures), "images": len(images),
        "animations": len(animations), "skins": len(skins), "accessors": len(accessors),
        "buffers": len(buffers), "bufferViews": len(buffer_views),
    }
    if not meshes:
        error("document contains no meshes")
    if not scenes:
        warn("document contains no scenes")

    triangles = 0
    vertices = 0
    primitives = 0
    missing_tangent = 0
    used_materials = set()
    for mesh_index, mesh in enumerate(meshes):
        for prim in mesh.get("primitives") or []:
            primitives += 1
            attributes = prim.get("attributes") or {}
            if "indices" in prim:
                triangles += accessor_count(document, prim["indices"]) // 3
            if "POSITION" in attributes:
                vertices += accessor_count(document, attributes["POSITION"])
            if "TANGENT" not in attributes:
                missing_tangent += 1
            if isinstance(prim.get("material"), int):
                used_materials.add(prim["material"])
            if not attributes:
                error("mesh %d has a primitive without attributes" % mesh_index)
    entry["triangles"] = triangles
    entry["vertices"] = vertices
    entry["primitives"] = primitives
    if args.max_triangles and triangles > args.max_triangles:
        warn("%d triangles exceed the agreed budget %d" % (triangles, args.max_triangles))

    entry["materials"] = []
    normals_used = False
    for index, material in enumerate(materials):
        pbr = material.get("pbrMetallicRoughness") or {}
        normal_texture = material.get("normalTexture")
        if normal_texture:
            normals_used = True
        record = {
            "index": index,
            "name": material.get("name"),
            "baseColorFactor": pbr.get("baseColorFactor"),
            "metallicFactor": pbr.get("metallicFactor"),
            "roughnessFactor": pbr.get("roughnessFactor"),
            "baseColorTexture": bool(pbr.get("baseColorTexture")),
            "metallicRoughnessTexture": bool(pbr.get("metallicRoughnessTexture")),
            "normalTexture": bool(normal_texture),
            "occlusionTexture": bool(material.get("occlusionTexture")),
            "emissiveTexture": bool(material.get("emissiveTexture")),
            "emissiveFactor": material.get("emissiveFactor"),
            "alphaMode": material.get("alphaMode") or "OPAQUE",
            "doubleSided": bool(material.get("doubleSided")),
            "used": index in used_materials,
        }
        entry["materials"].append(record)
        if record["metallicFactor"] is None and not record["metallicRoughnessTexture"]:
            note("material %d has no metallic information" % index)
        factor = record["baseColorFactor"]
        if isinstance(factor, list) and len(factor) >= 3:
            if all(abs(float(v) - 1.0) < 1e-6 for v in factor[:3]) and not record["baseColorTexture"]:
                warn("material %d is pure white with no base color texture" % index)
            if all(abs(float(v)) < 1e-6 for v in factor[:3]) and not record["baseColorTexture"]:
                warn("material %d is pure black with no base color texture" % index)
        if record["roughnessFactor"] == 0 and not record["metallicRoughnessTexture"]:
            warn("material %d has roughness 0; mirror-like surfaces are rarely correct" % index)
    if normals_used and missing_tangent:
        warn("%d primitive(s) lack TANGENT while normal maps are used; tangents will be recomputed or ignored" % missing_tangent)
    unused = [m["name"] or ("index %d" % m["index"]) for m in entry["materials"] if not m["used"]]
    if unused:
        note("unused materials: %s" % ", ".join(unused[:8]))

    entry["images"] = []
    for index, image in enumerate(images):
        record = {"index": index, "name": image.get("name"), "mimeType": image.get("mimeType"),
                  "uri": image.get("uri")}
        if "bufferView" in image:
            view_index = image["bufferView"]
            record["embedded"] = True
            if isinstance(view_index, int) and 0 <= view_index < len(buffer_views):
                record["bytes"] = buffer_views[view_index].get("byteLength")
            else:
                error("image %d references bufferView %s which does not exist" % (index, view_index))
        else:
            record["embedded"] = False
            uri = image.get("uri") or ""
            if uri and not uri.startswith("data:"):
                target = os.path.join(base_dir, uri)
                record["exists"] = os.path.isfile(target)
                if not record["exists"]:
                    error("image %d references a missing file: %s" % (index, uri))
        entry["images"].append(record)

    entry["buffers"] = []
    for index, buffer_item in enumerate(buffers):
        record = {"index": index, "byteLength": buffer_item.get("byteLength"),
                  "uri": buffer_item.get("uri")}
        uri = buffer_item.get("uri")
        if uri:
            if uri.startswith("data:"):
                record["embedded"] = True
            else:
                target = os.path.join(base_dir, uri)
                record["exists"] = os.path.isfile(target)
                record["embedded"] = False
                if not record["exists"]:
                    error("buffer %d references a missing file: %s" % (index, uri))
                size = os.path.getsize(target) if record["exists"] else 0
                declared = int(buffer_item.get("byteLength") or 0)
                if declared and size and size < declared:
                    error("buffer %d declares %d bytes but the file is %d bytes" % (index, declared, size))
        else:
            record["embedded"] = container["container"] == "glb"
            if not record["embedded"]:
                error("buffer %d has no uri in a JSON container" % index)
        entry["buffers"].append(record)

    extensions_used = document.get("extensionsUsed") or []
    extensions_required = document.get("extensionsRequired") or []
    entry["extensionsUsed"] = extensions_used
    entry["extensionsRequired"] = extensions_required
    for name in extensions_required:
        if name in COMPRESSION_EXTENSIONS:
            warn("required extension %s: viewers and engines without it cannot open this file" % name)
    for name in extensions_used:
        if name not in extensions_required:
            note("optional extension %s" % name)

    if skins:
        for index, skin in enumerate(skins):
            if not skin.get("joints"):
                error("skin %d has no joints" % index)
    if animations:
        entry["animation_channels"] = sum(len(a.get("channels") or []) for a in animations)
        entry["animation_samplers"] = sum(len(a.get("samplers") or []) for a in animations)
        note("%d animation(s): %s" % (len(animations), ", ".join(
            (a.get("name") or "unnamed") for a in animations[:6])))

    scales = []
    for node in nodes:
        scale = node.get("scale")
        if isinstance(scale, list) and any(abs(float(v) - 1.0) > 1e-6 for v in scale):
            scales.append(scale)
    if scales:
        note("non-unit node scales present (unit conversion hint): %s" % scales[:4])

    declared = container.get("declared_length") or 0
    if container["container"] == "glb":
        actual = entry["bytes"]
        if declared and abs(actual - declared) > 8:
            warn("GLB declares %d bytes but the file is %d bytes" % (declared, actual))
    return entry


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect glTF/GLB exports.")
    parser.add_argument("files", nargs="+", help=".gltf or .glb files")
    parser.add_argument("--check", action="store_true", help="fail on warnings too (exit code 1)")
    parser.add_argument("--max-triangles", type=int, default=0, help="budget warning threshold")
    parser.add_argument("--json", help="write the report to this path")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    results = []
    bad_input = False
    for path in args.files:
        if not os.path.isfile(path):
            print("error: file not found: %s" % path, file=sys.stderr)
            bad_input = True
            continue
        results.append(analyse(path, args))
    if bad_input and not results:
        return 2

    payload = {"tool": "gltf_report.py", "version": TOOL_VERSION, "files": results}
    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        except OSError as exc:
            print("error: cannot write %s: %s" % (args.json, exc), file=sys.stderr)
            return 2

    errors = warnings = 0
    if not args.quiet:
        for entry in results:
            print("=" * 72)
            print("%s  (%.2f MB, %s)" % (entry["path"], entry["bytes"] / 1048576.0,
                                         entry.get("container", {}).get("container", "?")))
            if "glTF_version" in entry:
                print("  version %s | generator %s" % (entry.get("glTF_version"), entry.get("generator")))
            if "counts" in entry:
                counts = entry["counts"]
                print("  nodes %(nodes)d | meshes %(meshes)d | materials %(materials)d | images %(images)d | "
                      "animations %(animations)d | skins %(skins)d" % counts)
            if "triangles" in entry:
                print("  triangles %d | vertices %d | primitives %d" % (
                    entry["triangles"], entry["vertices"], entry["primitives"]))
            for message in entry["errors"]:
                print("  ERROR  %s" % message)
            for message in entry["warnings"]:
                print("  WARN   %s" % message)
            for message in entry["info"]:
                print("  INFO   %s" % message)
            errors += len(entry["errors"])
            warnings += len(entry["warnings"])
    else:
        for entry in results:
            errors += len(entry["errors"])
            warnings += len(entry["warnings"])

    print("gltf_report %s: %d file(s), %d error(s), %d warning(s)" % (
        TOOL_VERSION, len(results), errors, warnings))
    if args.check and warnings:
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
