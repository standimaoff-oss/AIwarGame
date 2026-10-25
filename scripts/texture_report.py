#!/usr/bin/env python3
"""Texture set inspector. Standalone Python 3.9+, no third-party packages.

    python texture_report.py <paths...> [--recursive] [--check] [--json out.json]

Reads image headers directly (PNG, JPEG, WebP, TGA, BMP, EXR, Radiance HDR,
DDS), so Pillow is not required. Reports resolution, channels and bit depth,
groups files into texture sets by name and checks: power-of-two resolution,
maximum size, recognizable map suffix, set completeness, equal resolution
inside a set and the expected color space by map name. Never modifies files.
Exit code 0 = ok, 1 = check failures, 2 = bad arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys

TOOL_VERSION = "1.0.0"

MAP_TOKENS = {
    "basecolor": "BaseColor", "albedo": "BaseColor", "diffuse": "BaseColor", "color": "BaseColor",
    "roughness": "Roughness", "rough": "Roughness",
    "metallic": "Metallic", "metalness": "Metallic", "metal": "Metallic",
    "normal": "Normal", "normaldx": "NormalDX", "nrm": "Normal", "nor": "Normal",
    "height": "Height", "displacement": "Height", "disp": "Height",
    "ao": "AO", "occlusion": "AO", "ambientocclusion": "AO",
    "orm": "ORM", "rma": "ORM",
    "emissive": "Emissive", "emission": "Emissive", "selfillum": "Emissive",
    "opacity": "Opacity", "alpha": "Opacity", "mask": "Opacity", "transparency": "Opacity",
    "curvature": "Curvature", "cavity": "Curvature",
    "thickness": "Thickness",
    "sheen": "Sheen", "fuzz": "Sheen",
    "anisotropy": "Anisotropy",
    "specular": "Other", "spec": "Other", "ior": "Other",
}
NON_COLOR = {"Roughness", "Metallic", "Normal", "NormalDX", "Height", "AO", "ORM",
             "Curvature", "Thickness", "Anisotropy"}
SRGB = {"BaseColor", "Emissive"}
RES_TOKEN = re.compile(r"^(?:\d{3,5}|[1-9]\d?k)$", re.I)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tga", ".bmp", ".exr", ".hdr", ".dds", ".tif", ".tiff"}
SKIP_DIRS = {".git", "__pycache__", "renders", "poses", "references", "web_refs", "versions", "exports"}
REQUIRED_PER_SET = ("BaseColor",)
RECOMMENDED_PER_SET = ("Roughness", "Normal")


def is_power_of_two(value):
    return value > 0 and (value & (value - 1)) == 0


def read_header(path, limit=1 << 20):
    """Return dict(width, height, channels, bit_depth, format) or None."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(limit)
    except OSError:
        return None
    if len(head) < 12:
        return None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png(head)
    if head.startswith(b"\xff\xd8"):
        return _jpeg(head)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return _webp(head)
    if head[:2] == b"BM":
        return _bmp(head)
    if head[:4] == b"\x76\x2f\x31\x01":
        return _exr(head)
    if head[:2] == b"#\n" or head[:11] == b"#?RADIANCE\n" or b"#?RGBE" in head[:32]:
        return _hdr(head)
    if head[:4] == b"DDS ":
        return _dds(head)
    if len(head) >= 18:
        return _tga(head)
    return None


def _png(data):
    if len(data) < 33 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    bit_depth = data[24]
    color_type = data[25]
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    return {"width": width, "height": height, "channels": channels,
            "bit_depth": bit_depth, "format": "png",
            "note": "palette" if color_type == 3 else None}


def _jpeg(data):
    index = 2
    size = len(data)
    while index + 9 < size:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xD9:
            break
        length = struct.unpack(">H", data[index:index + 2])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            precision = data[index + 2]
            height, width = struct.unpack(">HH", data[index + 3:index + 7])
            components = data[index + 7]
            return {"width": width, "height": height, "channels": components,
                    "bit_depth": precision, "format": "jpeg"}
        index += length
    return None


def _webp(data):
    chunk = data[12:16]
    payload = data[20:]
    if chunk == b"VP8X" and len(payload) >= 10:
        width = 1 + (payload[4] | (payload[5] << 8) | (payload[6] << 16))
        height = 1 + (payload[7] | (payload[8] << 8) | (payload[9] << 16))
        alpha = bool(payload[0] & 0x10)
        return {"width": width, "height": height, "channels": 4 if alpha else 3,
                "bit_depth": 8, "format": "webp", "note": "extended"}
    if chunk == b"VP8 " and len(payload) >= 10:
        width = struct.unpack("<H", payload[6:8])[0] & 0x3FFF
        height = struct.unpack("<H", payload[8:10])[0] & 0x3FFF
        return {"width": width, "height": height, "channels": 3,
                "bit_depth": 8, "format": "webp", "note": "lossy"}
    if chunk == b"VP8L" and len(payload) >= 5:
        bits = struct.unpack("<I", payload[1:5])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        alpha = bool((bits >> 28) & 1)
        return {"width": width, "height": height, "channels": 4 if alpha else 3,
                "bit_depth": 8, "format": "webp", "note": "lossless"}
    return None


def _bmp(data):
    if len(data) < 30:
        return None
    width = struct.unpack("<i", data[18:22])[0]
    height = abs(struct.unpack("<i", data[22:26])[0])
    bpp = struct.unpack("<H", data[28:30])[0]
    return {"width": width, "height": height, "channels": max(1, bpp // 8),
            "bit_depth": min(bpp, 8), "format": "bmp"}


def _exr(data):
    index = 8
    size = len(data)
    channels = None
    window = None
    while index < size:
        end = data.find(b"\x00", index)
        if end < 0:
            break
        name = data[index:end].decode("ascii", "replace")
        index = end + 1
        end = data.find(b"\x00", index)
        if end < 0:
            break
        attr_type = data[index:end].decode("ascii", "replace")
        index = end + 1
        if index + 4 > size:
            break
        length = struct.unpack("<i", data[index:index + 4])[0]
        index += 4
        value = data[index:index + length]
        index += length
        if name == "channels" and attr_type == "chlist":
            channels = value.count(b"\x00") - value.count(b"\x00\x00\x00")
            names = re.findall(rb"[A-Za-z][A-Za-z0-9.]*", value)
            channels = max(1, len(set(names)))
        elif name == "dataWindow" and attr_type == "box2i" and len(value) >= 16:
            min_x, min_y, max_x, max_y = struct.unpack("<iiii", value[:16])
            window = (max_x - min_x + 1, max_y - min_y + 1)
        elif name == "" and attr_type == "":
            break
    if window is None:
        return None
    return {"width": window[0], "height": window[1], "channels": channels or 3,
            "bit_depth": 16, "format": "exr"}


def _hdr(data):
    text = data[:4096].decode("ascii", "replace")
    match = re.search(r"-Y\s+(\d+)\s+\+X\s+(\d+)", text)
    if not match:
        match = re.search(r"\+X\s+(\d+)\s+\+Y\s+(\d+)", text)
        if not match:
            return None
        width, height = int(match.group(1)), int(match.group(2))
    else:
        height, width = int(match.group(1)), int(match.group(2))
    return {"width": width, "height": height, "channels": 3,
            "bit_depth": 32, "format": "hdr"}


def _dds(data):
    if len(data) < 20:
        return None
    height, width = struct.unpack("<II", data[12:20])
    bpp = 0
    if len(data) >= 88:
        bpp = struct.unpack("<I", data[84:88])[0]
    return {"width": width, "height": height, "channels": 4,
            "bit_depth": min(bpp, 8) or 8, "format": "dds"}


def _tga(data):
    width = struct.unpack("<H", data[12:14])[0]
    height = struct.unpack("<H", data[14:16])[0]
    bpp = data[16]
    if width == 0 or height == 0 or bpp not in (1, 8, 15, 16, 24, 32):
        return None
    return {"width": width, "height": height, "channels": max(1, bpp // 8),
            "bit_depth": min(bpp, 8), "format": "tga"}


def parse_name(filename):
    """Return (slug, set, map, res_token) from a texture file name.

    Convention: [T_]<Asset>_<Set>_<Map>_<res>. The token right before the map
    name is the texture set, the tokens before it form the asset slug.
    """
    stem = os.path.splitext(filename)[0]
    parts = [p for p in re.split(r"[_\-\s]+", stem) if p]
    map_name = None
    map_index = None
    for index, part in enumerate(parts):
        key = part.lower()
        if key in MAP_TOKENS:
            map_name = MAP_TOKENS[key]
            map_index = index
            break
    res_token = None
    for part in parts:
        if RES_TOKEN.match(part):
            res_token = part.lower()
            break
    if map_index is None or map_index == 0:
        slug = "_".join(parts).lower() or stem.lower()
        return (slug, "default", map_name, res_token)
    prefix = parts[:map_index]
    set_name = prefix[-1].lower()
    slug_parts = prefix[:-1]
    if slug_parts and slug_parts[0].lower() == "t":
        slug_parts = slug_parts[1:]
    slug = "_".join(slug_parts).lower() if slug_parts else set_name
    return (slug, set_name, map_name, res_token)


def collect(paths, recursive):
    files = []
    for path in paths:
        if os.path.isfile(path):
            files.append(path)
        elif os.path.isdir(path):
            if recursive:
                for dirpath, dirnames, filenames in os.walk(path):
                    dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
                    for name in sorted(filenames):
                        files.append(os.path.join(dirpath, name))
            else:
                for name in sorted(os.listdir(path)):
                    candidate = os.path.join(path, name)
                    if os.path.isfile(candidate):
                        files.append(candidate)
        else:
            print("error: path does not exist: %s" % path, file=sys.stderr)
            return None
    return files


def analyse(files, args):
    entries = []
    errors = []
    warnings = []
    sets = {}
    for path in files:
        ext = os.path.splitext(path)[1].lower()
        name = os.path.basename(path)
        if ext not in IMAGE_EXT:
            continue
        size = os.path.getsize(path)
        info = read_header(path)
        slug, set_name, map_name, res_token = parse_name(name)
        entry = {
            "path": path.replace(os.sep, "/"),
            "name": name,
            "bytes": size,
            "slug": slug,
            "set": set_name,
            "map": map_name,
            "res_token": res_token,
            "expected_colorspace": ("Non-Color" if map_name in NON_COLOR
                                    else "sRGB" if map_name in SRGB
                                    else "Unknown"),
        }
        if info is None:
            entry["header"] = None
            errors.append("%s: cannot parse the image header (corrupted or unsupported format)" % entry["path"])
        else:
            entry["header"] = info
            width, height = info["width"], info["height"]
            if width <= 0 or height <= 0:
                errors.append("%s: invalid resolution %dx%d" % (entry["path"], width, height))
            if not (is_power_of_two(width) and is_power_of_two(height)):
                warnings.append("%s: resolution %dx%d is not a power of two" % (entry["path"], width, height))
            if max(width, height) > args.max_size:
                warnings.append("%s: resolution %dx%d exceeds the agreed maximum %d" % (
                    entry["path"], width, height, args.max_size))
            if width != height:
                warnings.append("%s: non-square texture %dx%d (UDIM or deliberate)" % (entry["path"], width, height))
            if res_token:
                expected = int(res_token.rstrip("k")) * 1024 if res_token.endswith("k") else int(res_token)
                if max(width, height) != expected:
                    warnings.append("%s: name says %s but the file is %dx%d" % (
                        entry["path"], res_token, width, height))
            if size > 60 * 1024 * 1024:
                warnings.append("%s: %.1f MB; keep large textures in Git LFS" % (entry["path"], size / 1048576.0))
        if map_name is None:
            warnings.append("%s: file name has no recognizable map suffix (BaseColor, Normal, ...)" % entry["path"])
        else:
            key = (slug, set_name)
            sets.setdefault(key, {})[map_name] = entry
        entries.append(entry)

    for (slug, set_name), maps in sorted(sets.items()):
        label = "%s/%s" % (slug, set_name)
        resolutions = {m["header"]["width"] for m in maps.values() if m.get("header")}
        if len(resolutions) > 1:
            errors.append("%s: texture set mixes resolutions %s" % (label, sorted(resolutions)))
        for required in REQUIRED_PER_SET:
            if required not in maps:
                errors.append("%s: set has no %s map" % (label, required))
        for recommended in RECOMMENDED_PER_SET:
            if recommended not in maps:
                warnings.append("%s: set has no %s map (add it or justify in the manifest)" % (label, recommended))
        if "BaseColor" in maps and "Roughness" not in maps and "ORM" not in maps:
            warnings.append("%s: no Roughness and no packed ORM map" % label)
        if "ORM" in maps and ("Roughness" in maps or "Metallic" in maps or "AO" in maps):
            warnings.append("%s: packed ORM and separate maps coexist; state which one the engine uses" % label)

    return entries, errors, warnings, sets


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect texture sets without external packages.")
    parser.add_argument("paths", nargs="+", help="files or folders with textures")
    parser.add_argument("--recursive", action="store_true", help="walk folders recursively")
    parser.add_argument("--check", action="store_true", help="treat findings as failures (exit code 1)")
    parser.add_argument("--max-size", type=int, default=8192, help="agreed maximum resolution (default 8192)")
    parser.add_argument("--json", help="write the report to this path")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    files = collect(args.paths, args.recursive)
    if files is None:
        return 2
    entries, errors, warnings, sets = analyse(files, args)

    payload = {
        "tool": "texture_report.py",
        "version": TOOL_VERSION,
        "paths": [p.replace(os.sep, "/") for p in args.paths],
        "recursive": args.recursive,
        "max_size": args.max_size,
        "file_count": len(entries),
        "sets": [
            {"slug": slug, "set": set_name,
             "maps": sorted(maps.keys()),
             "resolution": sorted({m["header"]["width"] for m in maps.values() if m.get("header")})}
            for (slug, set_name), maps in sorted(sets.items())
        ],
        "files": entries,
        "errors": errors,
        "warnings": warnings,
    }
    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        except OSError as exc:
            print("error: cannot write %s: %s" % (args.json, exc), file=sys.stderr)
            return 2

    if not args.quiet:
        for entry in entries:
            header = entry.get("header")
            if header:
                print("%-64s %-9s %-11s %5dx%-5d %2dch %2dbit %8.2f MB  %s" % (
                    entry["path"][:64], entry["map"] or "-", header["format"],
                    header["width"], header["height"], header.get("channels") or 0,
                    header.get("bit_depth") or 0, entry["bytes"] / 1048576.0,
                    entry["expected_colorspace"]))
            else:
                print("%-64s UNREADABLE HEADER" % entry["path"][:64])
        for message in errors:
            print("ERROR  %s" % message)
        for message in warnings:
            print("WARN   %s" % message)
    print("texture_report %s: %d file(s), %d set(s), %d error(s), %d warning(s)" % (
        TOOL_VERSION, len(entries), len(sets), len(errors), len(warnings)))

    if args.check and (errors or warnings):
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
