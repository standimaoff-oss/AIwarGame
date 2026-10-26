#!/usr/bin/env python3
"""Asset repository validator. Standalone Python 3.9+, no third-party packages.

    python validate_asset.py --root . [--asset assets/<slug>] [--strict]
                             [--json validation-report.json] [--check-lfs]

Checks repository conventions (LFS, structure, secrets, oversized files) and
every asset folder (TASK/asset-state, manifest schema and facts, texture files,
proofs, exports). Exit code 0 = no errors, 1 = errors found, 2 = bad arguments
or unreadable input. The script never modifies files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

TOOL_VERSION = "1.0.0"
MANIFEST_SCHEMA = 2

ARCHETYPES = {
    "architecture", "character", "hard_surface", "prop", "vehicle",
    "environment", "texture_set", "scene", "other",
}
STATUSES = {"wip", "review", "done", "blocked"}
MAPS = {
    "BaseColor", "Roughness", "Metallic", "Normal", "NormalDX", "Height",
    "AO", "Emissive", "Opacity", "Curvature", "Thickness", "Sheen",
    "Anisotropy", "ORM", "Other",
}
NON_COLOR_MAPS = {"Roughness", "Metallic", "Normal", "NormalDX", "Height", "AO",
                  "Curvature", "Thickness", "Anisotropy", "ORM"}
SRGB_MAPS = {"BaseColor", "Emissive"}
EXPORT_EXT = {
    "glb": ".glb", "gltf": ".gltf", "fbx": ".fbx", "obj": ".obj",
    "usd": ".usd", "usdz": ".usdz", "stl": ".stl", "ply": ".ply",
    "abc": ".abc", "other": "",
}
LFS_EXT = {
    ".blend", ".fbx", ".obj", ".glb", ".gltf", ".usd", ".usdz", ".abc", ".stl",
    ".ply", ".kra", ".psd", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff",
    ".exr", ".hdr", ".tga", ".mp4", ".mov", ".wav", ".zip",
}
FORBIDDEN_NAMES = {
    ".env", "credentials.json", "id_rsa", "id_ed25519", "token.txt",
}
FORBIDDEN_SUFFIXES = (".blend1", ".blend2", ".kra~", ".psd.tmp")
SECRET_PATTERNS = [
    ("github_pat", re.compile(r"github_pat_[0-9A-Za-z_]{20,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{20,}")),
    ("aws_access_key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("slack_token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("bearer_secret", re.compile(r"(?i)\b(?:api[_-]?key|secret|password|passwd)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("gh_token_env", re.compile(r"(?i)\bGH_TOKEN\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}")),
]
TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".yml", ".yaml", ".py", ".toml", ".ini", ".cfg",
    ".gitattributes", ".gitignore", ".sh", ".ps1", ".bat", ".csv", ".html", ".css",
}
NON_ASCII_NAME = re.compile(r"[^\x00-\x7F]")
SPACE_NAME = re.compile(r"\s")
EXPECTED_DIRS = ("references", "web_refs", "source", "textures", "renders", "audit", "manifest")


class Report:
    def __init__(self, root):
        self.root = root
        self.errors = []
        self.warnings = []
        self.info = []
        self.assets = []

    def error(self, where, message):
        self.errors.append({"where": where, "message": message})

    def warn(self, where, message):
        self.warnings.append({"where": where, "message": message})

    def note(self, where, message):
        self.info.append({"where": where, "message": message})

    def as_dict(self, strict):
        return {
            "tool": "validate_asset.py",
            "version": TOOL_VERSION,
            "root": self.root,
            "strict": strict,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "assets": self.assets,
        }


def rel(path, root):
    try:
        return os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        return path


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def is_power_of_two(value):
    return value > 0 and (value & (value - 1)) == 0


def git_output(root, args):
    try:
        proc = subprocess.run(
            ["git"] + args, cwd=root, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def lfs_tracked(root, path):
    out = git_output(root, ["check-attr", "filter", "--", path])
    if out is None:
        return None
    return out.endswith("lfs")


def check_repo(report, root, args):
    gitattributes = os.path.join(root, ".gitattributes")
    if os.path.isfile(gitattributes):
        text = open(gitattributes, "r", encoding="utf-8", errors="ignore").read()
        if "filter=lfs" not in text:
            report.warn(".gitattributes", "no Git LFS filters; binaries above 50-100 MB will be rejected by GitHub")
    else:
        report.warn(".gitattributes", "missing; copy references/templates/gitattributes before committing binaries")
    for name in ("README.md", ".gitignore"):
        if not os.path.isfile(os.path.join(root, name)):
            report.warn(name, "missing")
    if not os.path.isfile(os.path.join(root, "docs", "CONVENTIONS.md")):
        report.note("docs/CONVENTIONS.md", "missing; naming and texel density conventions are not recorded")

    workflows = []
    wf_dir = os.path.join(root, ".github", "workflows")
    if os.path.isdir(wf_dir):
        workflows = [n for n in sorted(os.listdir(wf_dir)) if n.endswith((".yml", ".yaml"))]
    if not workflows:
        report.note(".github/workflows", "no CI workflow; copy references/templates/asset-ci.yml")
    else:
        tools = os.path.join(root, "tools")
        if not os.path.isdir(tools):
            report.warn("tools/", "CI workflows exist but validator scripts are not copied into tools/")
        report.note(".github/workflows", "workflows: " + ", ".join(workflows))

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")]
        for name in filenames:
            path = os.path.join(dirpath, name)
            where = rel(path, root)
            lower = name.lower()
            if lower in FORBIDDEN_NAMES or lower.endswith(FORBIDDEN_SUFFIXES):
                report.error(where, "forbidden file in the repository")
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            ext = os.path.splitext(lower)[1]
            if size <= 200 and ext in LFS_EXT:
                try:
                    head = open(path, "r", encoding="utf-8", errors="ignore").read(120)
                except OSError:
                    head = ""
                if head.startswith("version https://git-lfs.github.com/spec/v1"):
                    report.error(where, "Git LFS pointer instead of content; run 'git lfs pull'")
                    continue
            limit_mb = args.max_file_mb
            warn_mb = args.warn_file_mb
            if size > limit_mb * 1024 * 1024:
                tracked = lfs_tracked(root, path) if args.check_lfs else None
                detail = ""
                if tracked is False:
                    detail = " (not tracked by Git LFS)"
                elif tracked is None and ext in LFS_EXT:
                    detail = " (LFS tracking not verified; pass --check-lfs inside a git work tree)"
                report.error(where, "file is %.1f MB, above the %s MB GitHub limit%s" % (size / 1048576.0, limit_mb, detail))
            elif size > warn_mb * 1024 * 1024:
                report.warn(where, "file is %.1f MB; keep large binaries in Git LFS" % (size / 1048576.0))
            if ext in TEXT_SUFFIXES or name in (".gitattributes", ".gitignore"):
                scan_secrets(report, path, where)


def scan_secrets(report, path, where):
    try:
        if os.path.getsize(path) > 5 * 1024 * 1024:
            return
        text = open(path, "r", encoding="utf-8", errors="ignore").read()
    except OSError:
        return
    for label, pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            snippet = match.group(0)[:24] + "..."
            report.error(where, "possible secret (%s): %s" % (label, snippet))
            return


def resolve_texture_path(root, asset_dir, value):
    if not isinstance(value, str) or not value:
        return None
    candidates = [
        os.path.join(root, value),
        os.path.join(asset_dir, value),
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return os.path.normpath(cand)
    return None


def check_manifest(report, root, asset_dir, slug, manifest_path, strict):
    try:
        data = read_json(manifest_path)
    except (OSError, ValueError) as exc:
        report.error(rel(manifest_path, root), "unreadable manifest: %s" % exc)
        return {}
    where = rel(manifest_path, root)
    if data.get("schema_version") != MANIFEST_SCHEMA:
        report.error(where, "schema_version must be %d" % MANIFEST_SCHEMA)
    identity = data.get("identity")
    if not isinstance(identity, dict):
        report.error(where, "identity block is missing")
        identity = {}
    else:
        if identity.get("slug") and identity["slug"] != slug:
            report.error(where, "identity.slug '%s' does not match folder '%s'" % (identity["slug"], slug))
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", str(identity.get("slug", ""))):
            report.warn(where, "identity.slug must be lowercase latin with hyphens")
        if identity.get("archetype") not in ARCHETYPES:
            report.error(where, "identity.archetype must be one of: %s" % ", ".join(sorted(ARCHETYPES)))
        if identity.get("status") not in STATUSES:
            report.error(where, "identity.status must be one of: %s" % ", ".join(sorted(STATUSES)))
        if not identity.get("name"):
            report.warn(where, "identity.name is empty")

    units = data.get("units")
    if not isinstance(units, dict):
        report.error(where, "units block is missing")
    else:
        scale = units.get("scale_length")
        if not isinstance(scale, (int, float)) or scale <= 0:
            report.error(where, "units.scale_length must be a positive number")
        if units.get("up_axis") not in ("Z", "Y"):
            report.warn(where, "units.up_axis should be Z or Y")

    dims = data.get("dimensions_mm")
    if not isinstance(dims, dict) or not isinstance(dims.get("bbox"), list) or len(dims.get("bbox", [])) != 3:
        report.error(where, "dimensions_mm.bbox must be [X, Y, Z] in millimetres")
    else:
        bbox = dims["bbox"]
        if not all(isinstance(v, (int, float)) for v in bbox):
            report.error(where, "dimensions_mm.bbox must contain numbers")
        elif any(abs(float(v)) <= 1e-6 for v in bbox):
            report.error(where, "dimensions_mm.bbox has a zero axis; measurement is incomplete")
        elif any(abs(float(v)) > 1e7 for v in bbox):
            report.warn(where, "dimensions_mm.bbox above 10 km; check units (mm expected)")
        if not dims.get("includes"):
            report.warn(where, "dimensions_mm.includes is empty: state what the bounding box contains")

    budget = data.get("budget")
    if not isinstance(budget, dict):
        report.error(where, "budget block is missing")
    else:
        tri = budget.get("triangles")
        limit = budget.get("triangles_limit")
        if isinstance(tri, (int, float)) and tri <= 0:
            report.warn(where, "budget.triangles is zero or negative")
        if isinstance(tri, (int, float)) and isinstance(limit, (int, float)) and tri > limit:
            msg = "budget.triangles %d exceeds the limit %d" % (tri, limit)
            report.error(where, msg) if strict else report.warn(where, msg)
        if not budget.get("material_sets") and not budget.get("texture_resolution"):
            report.warn(where, "budget has no material_sets or texture_resolution")

    textures = data.get("textures") or []
    sets = {}
    if not isinstance(textures, list):
        report.error(where, "textures must be a list")
        textures = []
    for index, item in enumerate(textures):
        label = "%s:textures[%d]" % (where, index)
        if not isinstance(item, dict):
            report.error(label, "entry is not an object")
            continue
        path = item.get("path")
        resolved = resolve_texture_path(root, asset_dir, path)
        if resolved is None:
            report.error(label, "texture file not found: %s" % path)
        map_name = item.get("map")
        if map_name not in MAPS:
            report.error(label, "map must be one of: %s" % ", ".join(sorted(MAPS)))
        colorspace = item.get("colorspace")
        if colorspace not in ("sRGB", "Non-Color", "Raw", "Unknown"):
            report.warn(label, "colorspace should be sRGB, Non-Color, Raw or Unknown")
        elif map_name in NON_COLOR_MAPS and colorspace == "sRGB":
            report.error(label, "%s must not be sRGB" % map_name)
        elif map_name in SRGB_MAPS and colorspace == "Non-Color":
            report.error(label, "%s must be sRGB" % map_name)
        width, height = item.get("width"), item.get("height")
        set_name = item.get("set") or "default"
        if isinstance(width, int) and isinstance(height, int):
            if width != height:
                report.warn(label, "non-square texture %dx%d" % (width, height))
            if not (is_power_of_two(width) and is_power_of_two(height)):
                report.warn(label, "resolution %dx%d is not a power of two" % (width, height))
            if width > 16384:
                report.warn(label, "resolution %d above 16384" % width)
            sets.setdefault(set_name, set()).add((width, height))
        elif item.get("map") != "Other":
            report.warn(label, "width/height are missing")
    for set_name, resolutions in sets.items():
        if len(resolutions) > 1:
            report.warn(where, "texture set '%s' mixes resolutions: %s" % (set_name, sorted(resolutions)))

    exports = data.get("exports") or []
    for index, item in enumerate(exports):
        label = "%s:exports[%d]" % (where, index)
        if not isinstance(item, dict):
            report.error(label, "entry is not an object")
            continue
        path = item.get("path")
        if not isinstance(path, str):
            report.error(label, "path is missing")
            continue
        resolved = resolve_texture_path(root, asset_dir, path)
        if resolved is None:
            report.error(label, "export file not found: %s" % path)
            continue
        fmt = item.get("format")
        expected = EXPORT_EXT.get(fmt)
        if fmt not in EXPORT_EXT:
            report.error(label, "format must be one of: %s" % ", ".join(sorted(EXPORT_EXT)))
        elif expected and not resolved.lower().endswith(expected):
            report.error(label, "format '%s' does not match file extension of %s" % (fmt, path))

    proofs = data.get("proofs") or []
    if not proofs:
        report.warn(where, "no proofs listed; every acceptance criterion needs evidence")
    for index, item in enumerate(proofs):
        label = "%s:proofs[%d]" % (where, index)
        if isinstance(item, dict) and item.get("path"):
            if resolve_texture_path(root, asset_dir, item["path"]) is None:
                report.error(label, "proof file not found: %s" % item["path"])
            if not item.get("criterion"):
                report.warn(label, "proof has no criterion; state what it proves")

    audit = data.get("audit")
    if isinstance(audit, dict) and audit.get("report"):
        report_path = resolve_texture_path(root, asset_dir, audit["report"])
        if report_path is None:
            report.warn(where, "audit.report not found: %s" % audit["report"])
        if audit.get("status") in ("FAIL", "ERROR", "not_run"):
            report.warn(where, "audit status is %s" % audit["status"])

    for key in ("collections", "materials", "rig", "provenance", "open_items"):
        if key not in data:
            report.note(where, "%s block is missing" % key)

    return data


def check_asset(report, root, asset_dir, args):
    slug = os.path.basename(os.path.normpath(asset_dir))
    entry = {"slug": slug, "path": rel(asset_dir, root), "status": "unknown"}
    strict = args.strict

    for name in ("TASK.md", "asset-state.md"):
        if not os.path.isfile(os.path.join(asset_dir, name)):
            msg = "missing %s" % name
            report.error(rel(asset_dir, root), msg) if strict else report.warn(rel(asset_dir, root), msg)
    if not os.path.isfile(os.path.join(asset_dir, "README.md")):
        report.note(rel(asset_dir, root), "missing README.md (use references/templates/asset-README.md)")

    for name in EXPECTED_DIRS:
        if not os.path.isdir(os.path.join(asset_dir, name)):
            report.warn(rel(asset_dir, root), "missing folder %s/" % name)

    if SPACE_NAME.search(slug) or NON_ASCII_NAME.search(slug):
        report.error(rel(asset_dir, root), "slug must be latin lowercase without spaces")

    web_refs = os.path.join(asset_dir, "web_refs")
    if os.path.isdir(web_refs) and os.listdir(web_refs) and not os.path.isfile(os.path.join(web_refs, "sources.md")):
        report.warn("web_refs/", "references are stored without sources.md (URL, view, variant, license)")

    manifest_dir = os.path.join(asset_dir, "manifest")
    manifest_path = os.path.join(manifest_dir, "asset-manifest.json")
    data = {}
    if os.path.isfile(manifest_path):
        data = check_manifest(report, root, asset_dir, slug, manifest_path, strict)
    else:
        report.error(rel(asset_dir, root), "missing manifest/asset-manifest.json")

    status = (data.get("identity") or {}).get("status", "unknown")
    archetype = (data.get("identity") or {}).get("archetype", "other")
    entry["status"] = status
    entry["archetype"] = archetype

    source_dir = os.path.join(asset_dir, "source")
    blends = []
    if os.path.isdir(source_dir):
        blends = [n for n in os.listdir(source_dir) if n.lower().endswith(".blend")]
    if status in ("review", "done") and archetype != "texture_set" and not blends:
        report.error("source/", "no .blend source while status is '%s'" % status)
    if len(blends) > 1:
        report.warn("source/", "several .blend files; name the current source in asset-state.md")

    renders_dir = os.path.join(asset_dir, "renders")
    renders = []
    if os.path.isdir(renders_dir):
        for dirpath, _dirnames, filenames in os.walk(renders_dir):
            renders.extend(f for f in filenames if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    if status in ("review", "done") and not renders:
        report.error("renders/", "no proof renders while status is '%s'" % status)
    elif not renders:
        report.warn("renders/", "no proof renders yet")
    entry["renders"] = len(renders)

    textures_dir = os.path.join(asset_dir, "textures")
    textures = []
    if os.path.isdir(textures_dir):
        textures = [n for n in os.listdir(textures_dir)
                    if n.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".tga", ".exr", ".tif", ".tiff"))]
    entry["texture_files"] = len(textures)
    for name in textures:
        if SPACE_NAME.search(name) or NON_ASCII_NAME.search(name):
            report.warn("textures/" + name, "file name contains spaces or non-ascii characters")
        if not re.search(r"(BaseColor|Roughness|Metallic|Normal|Height|AO|Emissive|Opacity|ORM|Curvature|Thickness|Sheen|Anisotropy)", name, re.I):
            report.warn("textures/" + name, "file name has no recognizable map suffix")

    listed = set()
    for item in data.get("textures") or []:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            listed.add(os.path.basename(item["path"].replace("\\", "/")))
    if textures:
        unlisted = sorted(set(textures) - listed)
        if unlisted:
            report.warn("textures/", "%d file(s) on disk are not listed in manifest textures: %s" % (
                len(unlisted), ", ".join(unlisted[:5])))
    if listed and not textures:
        report.note("textures/", "manifest lists textures but the folder is empty; check paths")

    if archetype != "texture_set" and not textures and status in ("review", "done"):
        report.warn("textures/", "no texture files while status is '%s'" % status)

    for dirpath, dirnames, filenames in os.walk(asset_dir):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            lower = name.lower()
            if lower in FORBIDDEN_NAMES or lower.endswith(FORBIDDEN_SUFFIXES):
                report.error(rel(os.path.join(dirpath, name), root), "forbidden file in the asset folder")

    report.assets.append(entry)
    return entry


def find_assets(root, wanted):
    assets_dir = os.path.join(root, "assets")
    if wanted:
        paths = []
        for item in wanted:
            candidate = item if os.path.isabs(item) else os.path.join(root, item)
            if not os.path.isdir(candidate):
                candidate = os.path.join(assets_dir, item)
            if os.path.isdir(candidate):
                paths.append(candidate)
            else:
                raise FileNotFoundError("asset folder not found: %s" % item)
        return paths
    if not os.path.isdir(assets_dir):
        return []
    return [os.path.join(assets_dir, name) for name in sorted(os.listdir(assets_dir))
            if os.path.isdir(os.path.join(assets_dir, name))]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a 3D asset repository.")
    parser.add_argument("--root", default=".", help="repository root (default: current folder)")
    parser.add_argument("--asset", action="append", help="asset folder or slug; repeatable; default: all under assets/")
    parser.add_argument("--strict", action="store_true", help="promote selected warnings to errors (CI mode)")
    parser.add_argument("--check-lfs", action="store_true", help="verify Git LFS tracking with git check-attr")
    parser.add_argument("--max-file-mb", type=float, default=100.0)
    parser.add_argument("--warn-file-mb", type=float, default=50.0)
    parser.add_argument("--json", help="write the machine-readable report to this path")
    parser.add_argument("--quiet", action="store_true", help="print only the summary line")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("error: root folder does not exist: %s" % root, file=sys.stderr)
        return 2

    report = Report(root)
    check_repo(report, root, args)
    try:
        assets = find_assets(root, args.asset)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not assets:
        report.warn("assets/", "no asset folders found under assets/")
    for asset_dir in assets:
        check_asset(report, root, asset_dir, args)

    payload = report.as_dict(args.strict)
    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
                handle.write("\n")
        except OSError as exc:
            print("error: cannot write %s: %s" % (args.json, exc), file=sys.stderr)
            return 2

    if not args.quiet:
        for item in report.errors:
            print("ERROR  %s: %s" % (item["where"], item["message"]))
        for item in report.warnings:
            print("WARN   %s: %s" % (item["where"], item["message"]))
        if not args.strict:
            for item in report.info:
                print("INFO   %s: %s" % (item["where"], item["message"]))
    print("validate_asset %s: %d asset(s), %d error(s), %d warning(s)%s" % (
        TOOL_VERSION, len(report.assets), len(report.errors), len(report.warnings),
        " [strict]" if args.strict else ""))
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
