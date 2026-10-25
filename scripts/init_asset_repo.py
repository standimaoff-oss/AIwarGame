#!/usr/bin/env python3
"""Asset repository scaffolding. Standalone Python 3.9+, no third-party packages.

    python init_asset_repo.py --root <repo> --asset <slug> [--kind architecture]
                              [--templates <dir>] [--no-tools] [--force] [--json out.json]

Creates the repository conventions (README, .gitattributes with Git LFS,
.gitignore, docs/CONVENTIONS.md, CI workflow, PR template, issue form) and the
asset folder (TASK.md, asset-state.md, manifest, audit config, subfolders).
Copies the standalone validators into tools/ so CI does not depend on the skill
repository. Existing files are never overwritten unless --force is given.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

TOOL_VERSION = "1.0.0"
KINDS = ("architecture", "character", "hard_surface", "prop", "vehicle", "environment", "texture_set", "scene", "other")
VALIDATORS = ("validate_asset.py", "texture_report.py", "gltf_report.py")
ASSET_DIRS = ("references", "web_refs", "source", "source/textures_src", "versions",
              "textures", "exports", "renders", "renders/poses", "audit", "manifest")
AUDIT_TEMPLATES = {
    "architecture": "audit-example-architecture.json",
    "character": "audit-example-character.json",
}

MINIMAL_README = """# {repo}

Репозиторий 3D-ассетов. Соглашения: [docs/CONVENTIONS.md](docs/CONVENTIONS.md).

## Структура

- `assets/<slug>/` — один ассет: `TASK.md`, `asset-state.md`, `source/`, `textures/`, `renders/`, `manifest/`, `audit/`, `exports/`
- `tools/` — скрипты проверок для CI
- `.github/workflows/asset-ci.yml` — валидация структуры, manifest, текстур и glTF-экспорта

## Проверки перед PR

```bash
python tools/validate_asset.py --root . --strict
python tools/texture_report.py assets --recursive --check
```

Крупные бинарные файлы ведутся через Git LFS: `git lfs install --local` до первого коммита.
"""

MANIFEST_STUB = {
    "schema_version": 2,
    "generated_by": "scripts/init_asset_repo.py",
    "source_file": "assets/{slug}/source/{slug}.blend",
    "identity": {
        "slug": "{slug}",
        "name": "{name}",
        "archetype": "{kind}",
        "variant": "",
        "version": "v000_intake",
        "status": "wip",
        "task_issue": None,
        "branch": "",
    },
    "units": {"unit": "m", "scale_length": 1.0, "up_axis": "Z", "export_up_axis": "Y", "unit_system": "metric"},
    "dimensions_mm": {"bbox": [0.0, 0.0, 0.0], "frame": 1, "includes": "", "scope": ""},
    "budget": {"triangles": 0, "triangles_limit": 0, "vertices": 0, "objects": 0,
               "material_sets": 0, "texture_resolution": "", "lods": 0, "udim_tiles": 0},
    "collections": [],
    "materials": [],
    "textures": [],
    "rig": {"type": "none", "armatures": [], "bones": 0, "controls": [], "shape_keys": [],
            "frame_start": 1, "frame_end": 1, "animation_kind": "none", "notes": ""},
    "exports": [],
    "proofs": [],
    "audit": {"config": "assets/{slug}/audit/audit-config.json", "report": "assets/{slug}/audit/audit-report.json",
              "status": "not_run", "checks_total": 0, "checks_failed": 0},
    "provenance": [],
    "open_items": ["контракт задачи не заполнен: TASK.md"],
}

SOURCES_MD = """# sources — найденные референсы

| Файл | URL | Что показывает | Ракурс | Зеркальный | Вариант | Лицензия | Использовано для |
|---|---|---|---|---|---|---|---|
|  |  |  |  | нет |  |  |  |

Правила: для каждого источника — ракурс и признак варианта; AI-изображения и игровые кадры пригодны только для общей конфигурации; ключевой размер подтверждается двумя независимыми источниками.
"""


def write_if_absent(path, content, force, created, overwritten):
    existed = os.path.isfile(path)
    if existed and not force:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    (overwritten if existed else created).append(path)
    return True


def copy_template(templates, name, destination, force, created, overwritten, substitutions=None):
    source = os.path.join(templates, name)
    if not os.path.isfile(source):
        return False
    with open(source, "r", encoding="utf-8") as handle:
        content = handle.read()
    if substitutions:
        for key, value in substitutions.items():
            content = content.replace("<%s>" % key, value).replace("{%s}" % key, value)
    return write_if_absent(destination, content, force, created, overwritten)


def scaffold_repo(root, templates, args, created, overwritten):
    repo_name = os.path.basename(os.path.normpath(root))
    write_if_absent(os.path.join(root, "README.md"), MINIMAL_README.format(repo=repo_name), args.force, created, overwritten)
    copy_template(templates, "gitattributes", os.path.join(root, ".gitattributes"), args.force, created, overwritten)
    copy_template(templates, "gitignore", os.path.join(root, ".gitignore"), args.force, created, overwritten)
    copy_template(templates, "CONVENTIONS.md", os.path.join(root, "docs", "CONVENTIONS.md"), args.force, created, overwritten)
    copy_template(templates, "asset-ci.yml", os.path.join(root, ".github", "workflows", "asset-ci.yml"), args.force, created, overwritten)
    copy_template(templates, "PULL_REQUEST_TEMPLATE.md", os.path.join(root, ".github", "PULL_REQUEST_TEMPLATE.md"), args.force, created, overwritten)
    copy_template(templates, "asset-request.yml", os.path.join(root, ".github", "ISSUE_TEMPLATE", "asset-request.yml"), args.force, created, overwritten)

    if args.tools:
        tools_dir = os.path.join(root, "tools")
        os.makedirs(tools_dir, exist_ok=True)
        for name in VALIDATORS:
            source = os.path.join(args.tools_src, name)
            destination = os.path.join(tools_dir, name)
            if not os.path.isfile(source):
                print("warn: validator not found, skipped: %s" % source, file=sys.stderr)
                continue
            if os.path.isfile(destination) and not args.force:
                continue
            existed = os.path.isfile(destination)
            shutil.copyfile(source, destination)
            (overwritten if existed else created).append(destination)
    return True


def scaffold_asset(root, templates, args, created, overwritten):
    slug = args.asset
    asset_dir = os.path.join(root, "assets", slug)
    for sub in ASSET_DIRS:
        os.makedirs(os.path.join(asset_dir, sub), exist_ok=True)
    for sub in ASSET_DIRS:
        keep = os.path.join(asset_dir, sub, ".gitkeep")
        if not os.path.isfile(keep):
            open(keep, "w", encoding="utf-8").close()
            created.append(keep)

    subs = {"slug": slug, "kind": args.kind, "name": args.name or slug}
    copy_template(templates, "TASK.md", os.path.join(asset_dir, "TASK.md"), args.force, created, overwritten, subs)
    copy_template(templates, "asset-state.md", os.path.join(asset_dir, "asset-state.md"), args.force, created, overwritten, subs)
    copy_template(templates, "asset-README.md", os.path.join(asset_dir, "README.md"), args.force, created, overwritten, subs)
    write_if_absent(os.path.join(asset_dir, "web_refs", "sources.md"), SOURCES_MD, args.force, created, overwritten)

    manifest = json.loads(json.dumps(MANIFEST_STUB))
    def fill(value):
        return value.format(slug=slug, kind=args.kind, name=args.name or slug) if isinstance(value, str) else value
    manifest["source_file"] = fill(manifest["source_file"])
    for key in ("slug", "name", "archetype", "version"):
        manifest["identity"][key] = fill(manifest["identity"][key])
    manifest["audit"]["config"] = fill(manifest["audit"]["config"])
    manifest["audit"]["report"] = fill(manifest["audit"]["report"])
    manifest["open_items"] = [fill(item) for item in manifest["open_items"]]
    manifest_path = os.path.join(asset_dir, "manifest", "asset-manifest.json")
    write_if_absent(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    args.force, created, overwritten)

    audit_name = AUDIT_TEMPLATES.get(args.kind, "audit-example.json")
    audit_written = copy_template(templates, audit_name, os.path.join(asset_dir, "audit", "audit-config.json"),
                                  args.force, created, overwritten)
    if not audit_written:
        copy_template(templates, "audit-example.json", os.path.join(asset_dir, "audit", "audit-config.json"),
                      args.force, created, overwritten)
    return asset_dir


def main(argv=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Scaffold an asset repository or a single asset folder.")
    parser.add_argument("--root", default=".", help="repository root (default: current folder)")
    parser.add_argument("--asset", required=True, help="asset slug: lowercase latin, hyphens")
    parser.add_argument("--kind", default="other", choices=KINDS, help="archetype (default: other)")
    parser.add_argument("--name", help="human readable asset name")
    parser.add_argument("--templates", default=os.path.join(script_dir, os.pardir, "references", "templates"),
                        help="folder with templates (default: ../references/templates next to the script)")
    parser.add_argument("--tools-src", default=script_dir, help="folder with validator scripts to copy into tools/")
    parser.add_argument("--no-tools", dest="tools", action="store_false", help="do not copy validators into tools/")
    parser.add_argument("--repo-only", action="store_true", help="scaffold repository files only")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    parser.add_argument("--json", help="write a summary report to this path")
    args = parser.parse_args(argv)

    slug = args.asset.strip().strip("/\\")
    if not slug or " " in slug or not all(c.isascii() and (c.isalnum() or c == "-") for c in slug) \
            or not slug.replace("-", "").isalnum() or slug != slug.lower():
        print("error: --asset must be a lowercase latin slug with hyphens, got: %s" % args.asset, file=sys.stderr)
        return 2

    root = os.path.abspath(args.root)
    templates = os.path.abspath(args.templates)
    if not os.path.isdir(templates):
        print("error: templates folder not found: %s (pass --templates)" % templates, file=sys.stderr)
        return 2
    os.makedirs(root, exist_ok=True)

    created, overwritten = [], []
    scaffold_repo(root, templates, args, created, overwritten)
    asset_dir = None
    if not args.repo_only:
        asset_dir = scaffold_asset(root, templates, args, created, overwritten)

    summary = {
        "tool": "init_asset_repo.py",
        "version": TOOL_VERSION,
        "root": root,
        "asset": slug,
        "kind": args.kind,
        "asset_dir": asset_dir,
        "created": [os.path.relpath(p, root).replace(os.sep, "/") for p in created],
        "overwritten": [os.path.relpath(p, root).replace(os.sep, "/") for p in overwritten],
        "next_steps": [
            "заполнить assets/%s/TASK.md и asset-state.md" % slug,
            "git lfs install --local && git add .gitattributes",
            "положить .blend в assets/%s/source/ и референсы в references/" % slug,
            "python tools/validate_asset.py --root . --strict",
        ],
    }
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print("init_asset_repo %s: root=%s asset=%s kind=%s" % (TOOL_VERSION, root, slug, args.kind))
    print("  created %d file(s), overwritten %d" % (len(summary["created"]), len(summary["overwritten"])))
    for path in summary["created"]:
        print("  + %s" % path)
    for path in summary["overwritten"]:
        print("  ~ %s" % path)
    for step in summary["next_steps"]:
        print("  → %s" % step)
    return 0


if __name__ == "__main__":
    sys.exit(main())
