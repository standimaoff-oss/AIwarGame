#!/usr/bin/env python3
"""Generate textured, component-separated glTF binary vehicle prototypes.

The GLBs are built from deterministic parametric geometry and embedded PBR maps.
The project uses these as editable starter assets, not photogrammetric replicas.
Requires Pillow: python -m pip install -r scripts/requirements-assets.txt
"""
from __future__ import annotations

import json
import math
import random
import struct
import zlib
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "models"
TEXTURE_SIZE = 512

# GLTF constants
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963
FLOAT = 5126
UNSIGNED_SHORT = 5123
UNSIGNED_INT = 5125
TRIANGLES = 4


def png_bytes(image: Image.Image) -> bytes:
    from io import BytesIO
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def create_pbr_textures(side: str) -> tuple[bytes, bytes, bytes]:
    rng = random.Random(94321 if side == "russia" else 60717)
    size = TEXTURE_SIZE
    canvas = Image.new("RGB", (size, size), "#596348" if side == "russia" else "#77745d")
    draw = ImageDraw.Draw(canvas, "RGB")
    palette = (
        ["#45543c", "#526243", "#68754f", "#858266", "#303c31", "#a09a72", "#5b6948"]
        if side == "russia" else
        ["#62644f", "#77775e", "#8e896f", "#a29979", "#4b5547", "#6c7057", "#928a6d"]
    )

    # Repeatable irregular brush shapes; duplicates crossing a border keep the texture tileable.
    for _ in range(105):
        cx, cy = rng.randrange(size), rng.randrange(size)
        rx, ry = rng.randint(10, 48), rng.randint(8, 32)
        points = []
        count = rng.randint(6, 11)
        for i in range(count):
            angle = math.tau * i / count
            radius = rng.uniform(.68, 1.28)
            points.append((cx + math.cos(angle) * rx * radius, cy + math.sin(angle) * ry * radius))
        color = rng.choice(palette)
        for ox in (-size, 0, size):
            for oy in (-size, 0, size):
                draw.polygon([(int(x + ox), int(y + oy)) for x, y in points], fill=color)

    # Fine surface grain and paint chips.
    pixels = canvas.load()
    for _ in range(26000):
        x, y = rng.randrange(size), rng.randrange(size)
        red, green, blue = pixels[x, y]
        delta = rng.choice((-18, -11, -6, 5, 9, 14))
        pixels[x, y] = (max(0, min(255, red + delta)), max(0, min(255, green + delta)), max(0, min(255, blue + delta)))
    for _ in range(310):
        x, y = rng.randrange(size), rng.randrange(size)
        length = rng.randint(3, 22)
        color = rng.choice(("#c1b88f", "#292f28", "#a8a17e"))
        draw.line((x, y, x + length, y + rng.choice((-2, -1, 0, 1, 2))), fill=color, width=rng.choice((1, 1, 2)))
    for _ in range(420):
        x, y = rng.randrange(size), rng.randrange(size)
        r = rng.choice((1, 1, 2))
        draw.ellipse((x-r, y-r, x+r, y+r), fill=rng.choice(("#b9ad82", "#30352b", "#74765d")))

    # A subtle luminance field provides seams, stamped panels and worn edges.
    height = Image.new("L", (size, size), 120)
    hd = ImageDraw.Draw(height)
    for y in range(18, size, 88):
        hd.line((0, y, size, y), fill=139, width=2)
    for x in range(22, size, 112):
        hd.line((x, 0, x, size), fill=133, width=1)
    for _ in range(450):
        x, y = rng.randrange(size), rng.randrange(size)
        hd.ellipse((x-2, y-2, x+2, y+2), fill=rng.randint(70, 190))
    height = height.filter(ImageFilter.GaussianBlur(0.55))
    h = height.load()
    normal = Image.new("RGB", (size, size))
    np = normal.load()
    for y in range(size):
        ym, yp = (y - 1) % size, (y + 1) % size
        for x in range(size):
            xm, xp = (x - 1) % size, (x + 1) % size
            nx = (h[xm, y] - h[xp, y]) * 0.018
            ny = (h[x, ym] - h[x, yp]) * 0.018
            nz = 1.0
            length = math.sqrt(nx*nx + ny*ny + nz*nz)
            np[x, y] = (int((nx/length*.5+.5)*255), int((ny/length*.5+.5)*255), int((nz/length*.5+.5)*255))

    # glTF metallic-roughness channels: R unused, G roughness, B metalness.
    mr = Image.new("RGB", (size, size))
    mrp = mr.load()
    for y in range(size):
        for x in range(size):
            grain = rng.randint(-18, 18)
            rough = max(0, min(255, 208 + grain + (12 if h[x, y] < 95 else 0)))
            metal = max(0, min(255, 28 + grain // 3))
            mrp[x, y] = (0, rough, metal)
    return png_bytes(canvas), png_bytes(normal), png_bytes(mr)


class GLB:
    def __init__(self, name: str, side: str):
        self.name = name
        self.side = side
        self.binary = bytearray()
        self.buffer_views: list[dict] = []
        self.accessors: list[dict] = []
        self.meshes: list[dict] = []
        self.nodes: list[dict] = [{"name": name, "children": []}]
        self.materials: list[dict] = []
        self.images: list[dict] = []
        self.textures: list[dict] = []
        self.samplers = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
        self._image_data: list[bytes] = []
        self._make_materials()

    def _align(self) -> None:
        while len(self.binary) % 4:
            self.binary.append(0)

    def _add_buffer_view(self, data: bytes, target: int | None = None) -> int:
        self._align()
        offset = len(self.binary)
        self.binary.extend(data)
        entry = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            entry["target"] = target
        self.buffer_views.append(entry)
        return len(self.buffer_views) - 1

    def _add_accessor(self, view: int, component_type: int, count: int, kind: str, minimum=None, maximum=None) -> int:
        accessor = {"bufferView": view, "componentType": component_type, "count": count, "type": kind}
        if minimum is not None:
            accessor["min"] = [float(v) for v in minimum]
        if maximum is not None:
            accessor["max"] = [float(v) for v in maximum]
        self.accessors.append(accessor)
        return len(self.accessors) - 1

    def _add_image(self, data: bytes, name: str) -> int:
        view = self._add_buffer_view(data)
        self.images.append({"name": name, "bufferView": view, "mimeType": "image/png"})
        return len(self.images) - 1

    def _make_materials(self) -> None:
        base, normal, mr = create_pbr_textures(self.side)
        image_ids = [
            self._add_image(base, f"{self.side}-camouflage-albedo"),
            self._add_image(normal, f"{self.side}-paint-normal"),
            self._add_image(mr, f"{self.side}-paint-metallic-roughness"),
        ]
        self.textures = [{"sampler": 0, "source": index} for index in image_ids]
        self.materials = [
            {"name": "Field paint · tiled camouflage", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicRoughnessTexture": {"index": 2}, "metallicFactor": 0.18, "roughnessFactor": 0.86}, "normalTexture": {"index": 1, "scale": 0.48}, "doubleSided": False},
            {"name": "Track rubber", "pbrMetallicRoughness": {"baseColorFactor": [0.075, 0.084, 0.075, 1], "metallicFactor": 0.04, "roughnessFactor": 0.94}},
            {"name": "Dark manganese steel", "pbrMetallicRoughness": {"baseColorFactor": [0.19, 0.21, 0.18, 1], "metallicFactor": 0.65, "roughnessFactor": 0.68}},
            {"name": "Brushed hardware", "pbrMetallicRoughness": {"baseColorFactor": [0.39, 0.4, 0.34, 1], "metallicFactor": 0.72, "roughnessFactor": 0.48}},
            {"name": "Optics and armored glass", "pbrMetallicRoughness": {"baseColorFactor": [0.055, 0.095, 0.09, 1], "metallicFactor": 0.24, "roughnessFactor": 0.2}},
            {"name": "Faction identification", "pbrMetallicRoughness": {"baseColorFactor": [0.58, 0.22, 0.14, 1] if self.side == "russia" else [0.16, 0.37, 0.52, 1], "metallicFactor": 0.12, "roughnessFactor": 0.64}},
            {"name": "Lamps and reflectors", "pbrMetallicRoughness": {"baseColorFactor": [0.91, 0.61, 0.23, 1], "metallicFactor": 0.1, "roughnessFactor": 0.3}},
        ]

    @staticmethod
    def _rotate(point, rotation):
        x, y, z = point
        rx, ry, rz = rotation
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)
        cz, sz = math.cos(rz), math.sin(rz)
        # Euler XYZ applied to vertices.
        y, z = y*cx-z*sx, y*sx+z*cx
        x, z = x*cy+z*sy, -x*sy+z*cy
        x, y = x*cz-y*sz, x*sz+y*cz
        return (x, y, z)

    def add_box(self, name: str, center, dims, material=0, rotation=(0, 0, 0)) -> None:
        cx, cy, cz = center
        w, h, d = dims
        hx, hy, hz = w/2, h/2, d/2
        faces = [
            ([( -hx,-hy, hz),( hx,-hy, hz),( hx, hy, hz),(-hx, hy, hz)], (0,0,1), w, h),
            ([( hx,-hy,-hz),(-hx,-hy,-hz),(-hx, hy,-hz),( hx, hy,-hz)], (0,0,-1), w, h),
            ([( hx,-hy, hz),( hx,-hy,-hz),( hx, hy,-hz),( hx, hy, hz)], (1,0,0), d, h),
            ([(-hx,-hy,-hz),(-hx,-hy, hz),(-hx, hy, hz),(-hx, hy,-hz)], (-1,0,0), d, h),
            ([(-hx, hy, hz),( hx, hy, hz),( hx, hy,-hz),(-hx, hy,-hz)], (0,1,0), w, d),
            ([(-hx,-hy,-hz),( hx,-hy,-hz),( hx,-hy, hz),(-hx,-hy, hz)], (0,-1,0), w, d),
        ]
        positions, normals, uvs, tangents, indices = [], [], [], [], []
        for corners, normal, uvw, uvh in faces:
            offset = len(positions)//3
            transformed = [self._rotate(p, rotation) for p in corners]
            n = self._rotate(normal, rotation)
            tangent = tuple(transformed[1][i]-transformed[0][i] for i in range(3))
            tlen = math.sqrt(sum(v*v for v in tangent)) or 1
            tangent = tuple(v/tlen for v in tangent)
            bitangent = tuple(transformed[3][i]-transformed[0][i] for i in range(3))
            cross_nt = (n[1]*tangent[2]-n[2]*tangent[1], n[2]*tangent[0]-n[0]*tangent[2], n[0]*tangent[1]-n[1]*tangent[0])
            handedness = 1.0 if sum(cross_nt[i]*bitangent[i] for i in range(3)) >= 0 else -1.0
            for j, p in enumerate(transformed):
                positions.extend((p[0]+cx, p[1]+cy, p[2]+cz))
                normals.extend(n)
                tangents.extend((*tangent, handedness))
                uv = ((0,0),(uvw*.22,0),(uvw*.22,uvh*.22),(0,uvh*.22))[j]
                uvs.extend(uv)
            indices.extend((offset, offset+1, offset+2, offset, offset+2, offset+3))
        self.add_mesh(name, positions, normals, uvs, tangents, indices, material)

    def add_cylinder(self, name: str, start, end, radius: float, material=0, segments=16, radius_end=None) -> None:
        if radius_end is None:
            radius_end = radius
        start, end = tuple(start), tuple(end)
        axis = tuple(end[i]-start[i] for i in range(3))
        length = math.sqrt(sum(v*v for v in axis)) or 1
        axis = tuple(v/length for v in axis)
        reference = (0,1,0) if abs(axis[1]) < .92 else (1,0,0)
        u = (axis[1]*reference[2]-axis[2]*reference[1], axis[2]*reference[0]-axis[0]*reference[2], axis[0]*reference[1]-axis[1]*reference[0])
        ulen = math.sqrt(sum(v*v for v in u)) or 1
        u = tuple(v/ulen for v in u)
        v = (axis[1]*u[2]-axis[2]*u[1], axis[2]*u[0]-axis[0]*u[2], axis[0]*u[1]-axis[1]*u[0])
        positions, normals, uvs, tangents, indices = [], [], [], [], []
        for ring, (point, rad) in enumerate(((start, radius), (end, radius_end))):
            for i in range(segments):
                angle = math.tau*i/segments
                radial = tuple(math.cos(angle)*u[k]+math.sin(angle)*v[k] for k in range(3))
                tangent = tuple(-math.sin(angle)*u[k]+math.cos(angle)*v[k] for k in range(3))
                positions.extend(point[k]+rad*radial[k] for k in range(3))
                normals.extend(radial)
                tangents.extend((*tangent, 1.0))
                uvs.extend((i/segments, ring*length*.22))
        for i in range(segments):
            nxt = (i+1)%segments
            a, b = i, nxt
            c, d = segments+nxt, segments+i
            indices.extend((a,b,c,a,c,d))
        # Caps, separate vertices keep cap normals and UVs correct.
        for point, rad, sign in ((start, radius, -1), (end, radius_end, 1)):
            normal = tuple(axis[k]*sign for k in range(3))
            center_index = len(positions)//3
            positions.extend(point)
            normals.extend(normal)
            tangents.extend((*u, float(sign)))
            uvs.extend((.5,.5))
            for i in range(segments):
                angle = math.tau*i/segments
                radial = tuple(math.cos(angle)*u[k]+math.sin(angle)*v[k] for k in range(3))
                positions.extend(point[k]+rad*radial[k] for k in range(3))
                normals.extend(normal)
                tangents.extend((*u, float(sign)))
                uvs.extend((.5+.5*math.cos(angle),.5+.5*math.sin(angle)))
            base = center_index+1
            for i in range(segments):
                nxt = (i+1)%segments
                if sign < 0:
                    indices.extend((center_index,base+nxt,base+i))
                else:
                    indices.extend((center_index,base+i,base+nxt))
        self.add_mesh(name, positions, normals, uvs, tangents, indices, material)

    def add_mesh(self, name, positions, normals, uvs, tangents, indices, material) -> None:
        p_bytes = struct.pack(f"<{len(positions)}f", *positions)
        n_bytes = struct.pack(f"<{len(normals)}f", *normals)
        uv_bytes = struct.pack(f"<{len(uvs)}f", *uvs)
        tangent_bytes = struct.pack(f"<{len(tangents)}f", *tangents)
        index_type = UNSIGNED_SHORT if max(indices, default=0) <= 65535 else UNSIGNED_INT
        code = "H" if index_type == UNSIGNED_SHORT else "I"
        i_bytes = struct.pack(f"<{len(indices)}{code}", *indices)
        p_view = self._add_buffer_view(p_bytes, ARRAY_BUFFER)
        n_view = self._add_buffer_view(n_bytes, ARRAY_BUFFER)
        uv_view = self._add_buffer_view(uv_bytes, ARRAY_BUFFER)
        tangent_view = self._add_buffer_view(tangent_bytes, ARRAY_BUFFER)
        i_view = self._add_buffer_view(i_bytes, ELEMENT_ARRAY_BUFFER)
        p_min = [min(positions[i::3]) for i in range(3)]
        p_max = [max(positions[i::3]) for i in range(3)]
        p_acc = self._add_accessor(p_view, FLOAT, len(positions)//3, "VEC3", p_min, p_max)
        n_acc = self._add_accessor(n_view, FLOAT, len(normals)//3, "VEC3")
        uv_acc = self._add_accessor(uv_view, FLOAT, len(uvs)//2, "VEC2")
        tangent_acc = self._add_accessor(tangent_view, FLOAT, len(tangents)//4, "VEC4")
        i_acc = self._add_accessor(i_view, index_type, len(indices), "SCALAR", [min(indices)], [max(indices)])
        self.meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": p_acc, "NORMAL": n_acc, "TEXCOORD_0": uv_acc, "TANGENT": tangent_acc}, "indices": i_acc, "material": material, "mode": TRIANGLES}]})
        node_index = len(self.nodes)
        self.nodes.append({"name": name, "mesh": len(self.meshes)-1})
        self.nodes[0]["children"].append(node_index)

    def save(self, path: Path) -> None:
        document = {
            "asset": {"version": "2.0", "generator": "AI WAR GAME · Procedural GLB Workshop", "copyright": "Procedurally generated game prototype"},
            "scene": 0,
            "scenes": [{"name": f"{self.name} / complete vehicle", "nodes": [0]}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "textures": self.textures,
            "images": self.images,
            "samplers": self.samplers,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.binary)}],
            "extras": {"side": self.side, "procedural": True, "pbr": "embedded albedo + normal + metallic/roughness textures", "revision": "v1"},
        }
        json_chunk = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        while len(json_chunk) % 4:
            json_chunk += b" "
        binary_chunk = bytes(self.binary)
        while len(binary_chunk) % 4:
            binary_chunk += b"\0"
        total_length = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
        glb = struct.pack("<4sII", b"glTF", 2, total_length)
        glb += struct.pack("<I4s", len(json_chunk), b"JSON") + json_chunk
        glb += struct.pack("<I4s", len(binary_chunk), b"BIN\0") + binary_chunk
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(glb)


def add_wheels(model: GLB, width: float, length: float, count: int, radius: float = .43, spacing: float = .8, track_thickness: float = .34) -> None:
    for side in (-1,1):
        x = side*(width/2 + track_thickness*.23)
        model.add_box("Continuous track belt", (x, radius, 0), (track_thickness, radius*1.12, length*.9), 1)
        # Tread blocks provide a visible toothed surface around the track run.
        for i in range(11):
            z = -length*.4 + i*(length*.8/10)
            model.add_box("Individual track shoe", (side*(width/2+track_thickness*.4), radius*1.68, z), (track_thickness*.85, .12, .31), 2)
        wheel_count = count
        for i in range(wheel_count):
            z = -length*.36 + i*(length*.72/max(wheel_count-1,1))
            model.add_cylinder("Road wheel / replaceable", (x-track_thickness*.6, radius, z), (x+track_thickness*.6, radius, z), radius, 1, 16)
            model.add_cylinder("Hub cap", (x+track_thickness*.6, radius, z), (x+track_thickness*.68, radius, z), radius*.28, 3, 12)
        for z, r, title in [(-length*.44, radius*1.12, "Idler wheel"),(length*.44, radius*1.2, "Drive sprocket")]:
            model.add_cylinder(title, (x-track_thickness*.62, radius, z), (x+track_thickness*.62, radius, z), r, 2, 18)


def make_tank(side: str) -> tuple[str, GLB]:
    russian = side == "russia"
    name = "Т-90М / T-90M" if russian else "M1A2 Abrams"
    model = GLB(name, side)
    w, length = (2.72,5.75) if russian else (2.96,6.65)
    model.add_box("Armored hull / cast steel", (0,1.02,-.05), (w,1.24,length), 0, (0,0,0))
    model.add_box("Sloped glacis plate", (0,1.66,2.03), (w*.91,.33,1.32), 0, (-.25,0,0))
    model.add_box("Rear engine deck", (0,1.66,-2.05), (w*.84,.42,1.42), 0, (0,0,0))
    model.add_box("Exhaust heat shield", (0,1.2,-3.01), (1.75,.34,.25), 2)
    add_wheels(model, w/2, length, 6, .42 if russian else .45, track_thickness=.38)
    for side_x in (-1,1):
        model.add_box("Side skirt / modular armor", (side_x*(w/2+.04),1.02,-.1), (.2,.52,4.1 if russian else 4.65), 0)
        for i in range(4):
            model.add_box("Side reactive armor tile", (side_x*(w/2+.16),1.23,-1.4+i*.82), (.08,.31,.64), 0)
        model.add_box("Front mud guard", (side_x*(w/2+.09),.83,2.78), (.27,.16,.32), 2)
        model.add_cylinder("Tow eye", (side_x*.74,.8,3.02),(side_x*.74,1.04,3.02),.12,3,10)
    model.add_cylinder("Turret race", (0,1.82,-.45),(0,2.08,-.45),.92,2,24)
    if russian:
        model.add_box("Low-profile turret base", (0,2.31,-.54), (2.13,.67,2.45), 0, (.02,-.1,0))
        model.add_box("Turret roof armor", (0,2.72,-.46), (1.84,.22,1.82), 0, (0,-.08,0))
        for sx in (-1,1):
            for i in range(3):
                model.add_box("ERA block / turret cheek", (sx*1.04,2.31,-.15+i*.53), (.26,.42,.43), 0, (0,sx*.12,0))
        for i in range(5):
            model.add_box("Relikt ERA roof tile", (-.72+i*.36,2.87,-.5), (.31,.1,.56), 0)
        barrel_start, barrel_end, barrel_radius = (0,2.47,.78),(0,2.48,4.5),.145
        model.add_box("Gun mantlet", (0,2.43,.82), (.91,.59,.77), 0)
        model.add_cylinder("125 mm main gun", barrel_start, barrel_end, barrel_radius, 3, 20)
        model.add_cylinder("Thermal sleeve", (0,2.48,1.25),(0,2.48,2.65),barrel_radius*1.34,0,18)
        model.add_cylinder("Muzzle brake", (0,2.48,4.35),(0,2.48,4.65),.21,2,18)
        model.add_cylinder("Commander cupola", (.54,2.86,-1.05),(.54,3.14,-1.05),.34,0,18)
        model.add_cylinder("Loader hatch", (-.56,2.84,-1.02),(-.56,3.03,-1.02),.28,0,16)
        model.add_box("Sosna-U sight housing", (-.79,2.68,.04), (.42,.4,.56), 4)
        for i in range(6):
            sx = -1 if i<3 else 1
            z = .58 + (i%3)*.24
            model.add_cylinder("Smoke grenade launcher", (sx*1.02,2.5,z),(sx*1.22,2.5,z+.04),.08,2,10)
        model.add_box("Rear bustle storage", (0,2.24,-1.97), (1.35,.55,.5), 0)
        model.add_box("Faction identification plate", (0,1.22,2.94), (1.0,.13,.035), 5)
    else:
        model.add_box("Abrams angular turret", (0,2.37,-.42), (2.62,.95,2.72), 0, (0,-.035,0))
        model.add_box("Turret roof plate", (0,2.91,-.35), (2.39,.18,2.18), 0)
        model.add_box("Gun mantlet", (0,2.5,.95), (1.06,.6,.72), 0)
        model.add_cylinder("120 mm smoothbore", (0,2.52,1.2),(0,2.54,5.18),.135,3,20)
        model.add_cylinder("Thermal sleeve", (0,2.54,1.58),(0,2.54,3.15),.18,0,18)
        model.add_cylinder("Bore evacuator", (0,2.54,3.24),(0,2.54,3.61),.23,0,18)
        model.add_cylinder("Muzzle reference sensor", (0,2.54,5.01),(0,2.54,5.2),.18,3,14)
        model.add_cylinder("Commander weapon station", (.72,3.02,-.82),(.72,3.33,-.82),.36,2,18)
        for sx in (-1,1):
            model.add_box("Turret bustle rack", (sx*1.08,2.23,-1.55), (.63,.45,.88), 0, (0,sx*.06,0))
            model.add_box("Abrams side armor package", (sx*(w/2+.03),1.08,-.3), (.19,.72,4.85), 0)
        model.add_box("CITV optic", (-.6,3.12,-.35), (.43,.45,.45), 4)
        model.add_box("Commander hatch", (.72,2.98,-.82), (.7,.12,.72), 0)
        model.add_box("Rear storage basket", (0,2.42,-2.03), (1.65,.62,.55), 2)
        model.add_box("Faction identification plate", (0,1.18,3.35), (1.0,.13,.035), 5)
    for sx in (-1,1):
        for i in range(3):
            model.add_box("IR lamp cluster", (sx*1.05,1.9,2.25+i*.24), (.19,.11,.12), 6)
        model.add_cylinder("Front tow hook", (sx*.78,.5,3.0),(sx*.78,.75,3.0),.1,3,10)
    return name, model


def make_ifv(side: str) -> tuple[str, GLB]:
    russian = side == "russia"
    name = "БМП-3 / BMP-3" if russian else "M2 Bradley"
    model = GLB(name, side)
    w, length = (2.86,5.75) if russian else (3.12,6.25)
    model.add_box("Armored hull", (0,1.02,-.02), (w,1.3,length), 0)
    model.add_box("Sloped front armor", (0,1.62,2.13), (w*.92,.39,1.12), 0, (-.29,0,0))
    model.add_box("Rear troop ramp", (0,1.2,-2.92), (w*.75,.82,.17), 2)
    add_wheels(model, w/2, length, 6, .4, track_thickness=.35)
    for sx in (-1,1):
        model.add_box("Side skirt", (sx*(w/2+.08),.91,-.25), (.18,.43,4.55), 0)
        for i in range(4):
            model.add_box("Side reactive armor tile", (sx*(w/2+.18),1.08,-1.38+i*.79), (.08,.26,.55), 0)
    model.add_cylinder("Turret race", (0,1.72,.24),(0,1.98,.24),.75,2,20)
    if russian:
        model.add_box("BMP-3 low turret", (0,2.23,.27), (1.62,.57,1.66), 0, (0,-.08,0))
        model.add_box("100 mm gun mantlet", (0,2.25,1.0), (.66,.41,.5), 0)
        model.add_cylinder("100 mm low-pressure cannon", (0,2.23,1.15),(0,2.23,3.42),.12,3,16)
        model.add_cylinder("30 mm autocannon", (-.31,2.11,1.25),(-.31,2.11,2.95),.075,3,14)
        model.add_cylinder("Commander sight", (.57,2.56,.12),(.57,2.83,.12),.16,4,14)
        model.add_box("Turret roof hatch", (-.35,2.57,-.05), (.53,.12,.58), 0)
        model.add_box("Faction identification plate", (0,1.3,2.96), (1.0,.12,.03), 5)
    else:
        model.add_box("Bradley turret", (0,2.39,.08), (2.02,.88,1.96), 0)
        model.add_box("Turret roof panel", (0,2.9,.05), (1.82,.16,1.65), 0)
        model.add_cylinder("25 mm Bushmaster autocannon", (0,2.49,1.0),(0,2.5,3.1),.11,3,18)
        model.add_box("TOW launcher housing", (1.21,2.53,-.15), (.46,.43,1.3), 0)
        model.add_box("TOW sight unit", (-.86,2.75,.14), (.46,.48,.5), 4)
        model.add_cylinder("Commander cupola", (.58,2.91,-.52),(.58,3.16,-.52),.29,0,16)
        model.add_box("Faction identification plate", (0,1.28,3.22), (1.0,.12,.03), 5)
    for sx in (-1,1):
        for i in range(3):
            model.add_cylinder("Smoke discharger", (sx*1.05,2.04,.44+i*.22),(sx*1.25,2.04,.49+i*.22),.075,2,10)
    return name, model


def make_truck(side: str) -> tuple[str, GLB]:
    russian = side == "russia"
    name = "Урал-4320 / Ural" if russian else "HMMWV"
    model = GLB(name, side)
    if russian:
        model.add_box("Ladder frame chassis", (0,.76,-.05), (2.08,.42,6.3), 2)
        model.add_box("Cab lower shell", (0,1.55,2.05), (2.12,1.28,2.1), 0)
        model.add_box("Cab windshield", (0,2.06,3.13), (1.84,.73,.08), 4, (-.12,0,0))
        model.add_box("Hood", (0,1.72,3.08), (1.98,.48,1.0), 0, (-.09,0,0))
        model.add_box("Cargo bed floor", (0,1.05,-1.65), (2.05,.18,3.45), 2)
        for sx in (-1,1):
            model.add_box("Cargo sideboard", (sx*.98,1.65,-1.65), (.1,1.18,3.45), 0)
            model.add_box("Cab side glass", (sx*1.075,2.02,1.92), (.06,.55,.92), 4)
            for z in (-2.25,-.2,1.95):
                model.add_cylinder("Heavy truck wheel", (sx*1.15,.58,z),(sx*1.42,.58,z),.47,1,16)
                model.add_cylinder("Wheel hub", (sx*1.42,.58,z),(sx*1.46,.58,z),.18,3,12)
        model.add_box("Faction identification plate", (0,.98,3.18), (1.0,.12,.03), 5)
        model.add_box("Roof canvas / supply cover", (0,2.52,-1.58), (1.83,.47,2.9), 0)
    else:
        model.add_box("Utility ladder frame", (0,.62,0), (1.95,.37,4.9), 2)
        model.add_box("HMMWV tub armor", (0,.99,-.03), (2.0,.68,4.5), 0)
        model.add_box("Front hood", (0,1.35,1.55), (2.02,.55,1.35), 0)
        model.add_box("Cab roof", (0,2.18,.05), (2.0,.18,2.1), 0)
        model.add_box("Windshield glass", (0,1.8,1.03), (1.72,.65,.07), 4, (-.18,0,0))
        for sx in (-1,1):
            model.add_box("Cab side glass", (sx*1.01,1.77,.03), (.06,.53,1.05), 4)
            model.add_cylinder("Utility tire", (sx*1.08,.57,-1.62),(sx*1.39,.57,-1.62),.48,1,16)
            model.add_cylinder("Utility tire", (sx*1.08,.57,1.62),(sx*1.39,.57,1.62),.48,1,16)
            model.add_cylinder("Wheel hub", (sx*1.39,.57,-1.62),(sx*1.43,.57,-1.62),.19,3,12)
            model.add_cylinder("Wheel hub", (sx*1.39,.57,1.62),(sx*1.43,.57,1.62),.19,3,12)
        model.add_box("Rear utility deck", (0,1.25,-1.56), (1.75,.25,1.25), 0)
        model.add_cylinder("Rear spare tire", (0,1.25,-2.32),(.24,1.25,-2.32),.48,1,16)
        model.add_box("Faction identification plate", (0,.88,2.34), (1.0,.12,.03), 5)
    model.add_box("Front bumper", (0,.56,3.25 if russian else 2.44), (2.34,.24,.22), 2)
    for sx in (-1,1):
        model.add_cylinder("Headlamp", (sx*.78,1.4,3.2 if russian else 2.25),(sx*.78,1.55,3.2 if russian else 2.25),.13,6,12)
    return name, model


def build_assets() -> None:
    generators = [make_tank, make_ifv, make_truck]
    for side in ("russia", "usa"):
        for generator in generators:
            name, model = generator(side)
            slug = {
                ("russia", "tank"): "t-90m", ("usa", "tank"): "m1a2-abrams",
                ("russia", "ifv"): "bmp-3", ("usa", "ifv"): "m2-bradley",
                ("russia", "truck"): "ural-4320", ("usa", "truck"): "hmmwv",
            }[(side, "tank" if generator is make_tank else "ifv" if generator is make_ifv else "truck")]
            path = OUT / f"{slug}.glb"
            model.save(path)
            print(f"{path.relative_to(ROOT)} · {path.stat().st_size/1024:.0f} KB · {name}")


if __name__ == "__main__":
    build_assets()
