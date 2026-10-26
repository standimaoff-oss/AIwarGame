#!/usr/bin/env python3
"""Generate the procedural 1K PBR texture sets used by the WWII Soviet arms assets.

Run with the sandbox Python that has Pillow and NumPy installed, e.g.

    python3 scripts/generate_wwii_textures.py --root .

All maps are original procedural images created for this repository. No third-party
texture is imported. Each set contains BaseColor, Roughness, Metallic, Normal and AO
maps with matching 1024x1024 resolution. BaseColor is sRGB; all other maps are data.
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, PngImagePlugin

SIZE = 1024
MAPS = ("BaseColor", "Roughness", "Metallic", "Normal", "AO")
SETS = ("BluedSteel", "ParkerizedSteel", "Wood", "Bakelite", "Brass", "Glass")
SLUGS = ("ppsh-41", "mosin-m91-30", "mosin-m91-30-pu", "nagant-m1895")


def save_png(path: Path, array: np.ndarray, note: str) -> None:
    arr = np.clip(array, 0, 255).astype(np.uint8)
    if arr.ndim == 2:
        image = Image.fromarray(arr, mode="L")
    else:
        image = Image.fromarray(arr, mode="RGB")
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", note)
    info.add_text("Source", "Procedural generation: scripts/generate_wwii_textures.py")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True, pnginfo=info)


def gray(value: float, noise: np.ndarray, contrast: float = 0.0) -> np.ndarray:
    return np.clip(value * 255.0 + noise * contrast, 0, 255)


def color(rgb: tuple[float, float, float], noise: np.ndarray, contrast: float = 0.0) -> np.ndarray:
    result = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    for channel, base in enumerate(rgb):
        result[..., channel] = base * 255.0 + noise * contrast
    return np.clip(result, 0, 255)


def normal_from_height(height: np.ndarray, strength: float = 3.0) -> np.ndarray:
    # Periodic gradients keep the map tileable.
    dx = np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)
    dy = np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)
    nx = -dx * strength
    ny = -dy * strength
    nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / length, ny / length, nz / length
    out = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    out[..., 0] = (nx * 0.5 + 0.5) * 255.0
    out[..., 1] = (ny * 0.5 + 0.5) * 255.0
    out[..., 2] = (nz * 0.5 + 0.5) * 255.0
    return out


def blurred_noise(rng: np.random.Generator, scale: float, blur: float) -> np.ndarray:
    coarse = rng.normal(0.0, scale, (64, 64)).astype(np.float32)
    image = Image.fromarray(np.clip(coarse * 12.0 + 128.0, 0, 255).astype(np.uint8), mode="L")
    image = image.resize((SIZE, SIZE), Image.Resampling.BICUBIC)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    return (np.asarray(image, dtype=np.float32) - 128.0) / 128.0


def periodic_wood_grain(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    grain = np.sin(xx * 0.075 + np.sin(yy * 0.014) * 4.0 + rng.uniform(0, 6.28))
    grain += 0.45 * np.sin(xx * 0.021 + yy * 0.006 + rng.uniform(0, 6.28))
    fine = np.sin(xx * 0.38 + np.sin(yy * 0.03) * 2.0) * 0.22
    broad = blurred_noise(rng, 0.65, 3.0)
    height = grain * 0.55 + fine + broad * 0.35
    # A few elongated darker pores, still tileable in the X direction.
    pores = np.zeros_like(height)
    for _ in range(90):
        cx = int(rng.integers(0, SIZE))
        cy = int(rng.integers(0, SIZE))
        width = int(rng.integers(2, 9))
        length = int(rng.integers(25, 180))
        shade = rng.uniform(-0.7, -0.2)
        xs = (np.arange(length) + cx) % SIZE
        for w in range(width):
            pores[(cy + w) % SIZE, xs] = shade
    height += pores
    return height, broad


def make_set(name: str, rng: np.random.Generator) -> dict[str, np.ndarray]:
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    fine = rng.normal(0.0, 1.0, (SIZE, SIZE)).astype(np.float32)
    broad = blurred_noise(rng, 0.8, 2.0)
    scratch_field = np.zeros_like(fine)
    # Directional scratches: thin periodic-ish lines with random lengths.
    for _ in range(220):
        cy = int(rng.integers(0, SIZE))
        start = int(rng.integers(0, SIZE - 220))
        length = int(rng.integers(35, 210))
        amp = rng.uniform(-0.35, 0.35)
        scratch_field[cy, start:start + length] += amp

    if name == "BluedSteel":
        brushed = np.sin(yy * 0.55) * 0.035 + np.sin(yy * 0.045 + xx * 0.003) * 0.025
        height = brushed + fine * 0.010 + scratch_field * 0.10
        base = color((0.021, 0.029, 0.039), height, 6.0)
        rough = gray(0.38, height * 0.18 + broad * 0.08, 9.0)
        metallic = np.full((SIZE, SIZE), 255, dtype=np.uint8)
        ao = gray(0.92, broad * 0.05 + fine * 0.012, 8.0)
    elif name == "ParkerizedSteel":
        grain = np.sin(xx * 0.22) * np.sin(yy * 0.19) * 0.045 + broad * 0.10
        height = grain + fine * 0.018 + scratch_field * 0.06
        base = color((0.036, 0.037, 0.035), height, 6.0)
        rough = gray(0.62, height * 0.15, 10.0)
        metallic = np.full((SIZE, SIZE), 255, dtype=np.uint8)
        ao = gray(0.88, broad * 0.06 + fine * 0.015, 10.0)
    elif name == "Wood":
        height, wood_broad = periodic_wood_grain(rng)
        tone = 0.5 + 0.5 * np.sin(height * 2.2 + wood_broad * 1.2)
        base_rgb = np.array((43.0, 22.0, 10.0), dtype=np.float32)
        highlight = np.array((112.0, 61.0, 28.0), dtype=np.float32)
        base = base_rgb[None, None, :] * (1.0 - tone[..., None] * 0.52) + highlight[None, None, :] * tone[..., None] * 0.52
        base += broad[..., None] * 4.0
        rough = gray(0.44, height * 0.09 + broad * 0.06, 9.0)
        metallic = np.zeros((SIZE, SIZE), dtype=np.uint8)
        ao = gray(0.90, height * 0.08 + broad * 0.05, 8.0)
    elif name == "Bakelite":
        mottle = np.sin(xx * 0.025 + yy * 0.017) * 0.12 + np.sin(xx * 0.09 - yy * 0.04) * 0.05 + broad * 0.14
        height = mottle + fine * 0.018
        base = color((0.035, 0.023, 0.016), height, 9.0)
        rough = gray(0.62, height * 0.10, 8.0)
        metallic = np.zeros((SIZE, SIZE), dtype=np.uint8)
        ao = gray(0.90, broad * 0.05, 8.0)
    elif name == "Brass":
        brushed = np.sin(yy * 0.50) * 0.035 + np.sin(yy * 0.16 + xx * 0.003) * 0.025
        height = brushed + fine * 0.010 + scratch_field * 0.10
        base = color((0.38, 0.27, 0.095), height, 8.0)
        rough = gray(0.34, height * 0.16, 9.0)
        metallic = np.full((SIZE, SIZE), 255, dtype=np.uint8)
        ao = gray(0.95, broad * 0.03, 6.0)
    elif name == "Glass":
        height = np.sin(xx * 0.015) * 0.02 + np.sin(yy * 0.013) * 0.02 + fine * 0.003
        base = color((0.025, 0.060, 0.070), height, 5.0)
        rough = gray(0.065, height * 0.05, 3.0)
        metallic = np.zeros((SIZE, SIZE), dtype=np.uint8)
        ao = gray(0.98, broad * 0.01, 3.0)
    else:
        raise ValueError(name)

    normal = normal_from_height(height, strength=1.1 if name in {"Wood", "Bakelite"} else 0.55)
    return {
        "BaseColor": base,
        "Roughness": rough,
        "Metallic": metallic.astype(np.float32),
        "Normal": normal,
        "AO": ao,
    }


def main() -> None:
    global SIZE
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--size", type=int, default=SIZE)
    args = parser.parse_args()
    SIZE = args.size
    root = Path(args.root).resolve()
    generated = {}
    seeds = {
        "BluedSteel": 4101,
        "ParkerizedSteel": 5201,
        "Wood": 6301,
        "Bakelite": 7401,
        "Brass": 8501,
        "Glass": 9601,
    }
    for set_name in SETS:
        rng = np.random.default_rng(seeds[set_name])
        generated[set_name] = make_set(set_name, rng)

    for slug in SLUGS:
        out_dir = root / "assets" / slug / "textures"
        out_dir.mkdir(parents=True, exist_ok=True)
        for set_name, maps in generated.items():
            for map_name, array in maps.items():
                path = out_dir / f"T_{slug}_{set_name}_{map_name}_1k.png"
                save_png(path, array, f"{set_name} {map_name}; procedural; {SIZE}x{SIZE}")
        print(f"textures: {slug}: {len(generated) * len(MAPS)} maps in {out_dir}")

    readme = root / "assets" / "TEXTURES.md"
    readme.write_text(
        "# Procedural PBR texture sets\n\n"
        "Each asset folder has a complete `textures/` set at 1024×1024. Maps are generated by "
        "`scripts/generate_wwii_textures.py`; no third-party texture is bundled. "
        "BaseColor is sRGB, other maps are Non-Color. Glass uses a dark optical coating in "
        "BaseColor; lens transmission is controlled by the material node, not by the raster map.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
