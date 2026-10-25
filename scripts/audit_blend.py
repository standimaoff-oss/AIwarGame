"""Read-only scene audit. Run with Blender, not a standalone Python interpreter.

blender --factory-startup --background FILE.blend --python audit_blend.py -- \
    --output report.json [--config config.json]

No .blend is saved. Only the JSON report is written. With a config, exact object
and collection names define each inspection's scope. Geometry measurements use
the evaluated mesh in world space. Units follow scene.unit_settings.scale_length.
PASS/FAIL is reserved for the explicitly supplied acceptance criteria.
"""

import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import tessellate_polygon


VERSION = 1
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}


def finite(values):
    return all(math.isfinite(float(value)) for value in values)


def matrix_values(matrix):
    return [float(value) for row in matrix for value in row]


def clean_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(item) for item in value]
    return value


def reject_unknown(spec, allowed, label):
    unknown = set(spec) - set(allowed)
    if unknown:
        raise ValueError(label + ": unknown configuration fields: " + ", ".join(sorted(unknown)))


class Auditor:
    def __init__(self, scene, configured):
        self.scene = scene
        self.configured = configured
        self.mm = float(scene.unit_settings.scale_length) * 1000.0
        if not math.isfinite(self.mm) or self.mm <= 0:
            raise ValueError("scene scale_length must be finite and positive")
        self.checks = []

    def check(self, label, passed, actual=None, expected=None):
        item = {"criterion": label, "status": "PASS" if passed else "FAIL"}
        if actual is not None:
            item["actual"] = actual
        if expected is not None:
            item["expected"] = expected
        self.checks.append(item)

    def info(self, label, detail):
        self.checks.append({"criterion": label, "status": "INFO", "detail": detail})

    def select(self, spec, label):
        objects = {}
        for name in spec.get("objects", []):
            obj = bpy.data.objects.get(name)
            self.check(label + "/object_exists/" + name, obj is not None)
            if obj is not None:
                objects[obj.name] = obj
        for name in spec.get("collections", []):
            collection = bpy.data.collections.get(name)
            self.check(label + "/collection_exists/" + name, collection is not None)
            if collection is not None:
                objects.update((obj.name, obj) for obj in collection.all_objects)
        if not spec.get("objects") and not spec.get("collections"):
            if self.configured:
                raise ValueError(label + " needs explicit objects or collections")
            objects = {obj.name: obj for obj in self.scene.objects}
        if self.configured:
            self.check(label + "/scope_nonempty", bool(objects))
        return sorted(objects.values(), key=lambda obj: obj.name)

    def geometry(self, obj, depsgraph):
        evaluated = obj.evaluated_get(depsgraph)
        if evaluated.type not in GEOMETRY_TYPES:
            return [], [], []
        mesh = evaluated.to_mesh()
        if mesh is None:
            return [], [], []
        try:
            vertices = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
            polygons = [tuple(poly.vertices) for poly in mesh.polygons]
            edges = [tuple(edge.vertices) for edge in mesh.edges]
            return vertices, polygons, edges
        finally:
            evaluated.to_mesh_clear()

    def bounds(self, geometries):
        vertices = [point for geometry in geometries for point in geometry[0]]
        if not vertices or not finite(value for point in vertices for value in point):
            return None
        low = [min(point[axis] for point in vertices) for axis in range(3)]
        high = [max(point[axis] for point in vertices) for axis in range(3)]
        return {
            "min_mm": [value * self.mm for value in low],
            "max_mm": [value * self.mm for value in high],
            "dimensions_mm": [(high[i] - low[i]) * self.mm for i in range(3)],
            "measurement": "evaluated world vertices; union over selected geometry",
        }

    def topology(self, vertices, polygons, edges, epsilon_mm2):
        usage = {tuple(sorted(edge)): 0 for edge in edges}
        zero_area = 0
        nonfinite_vertices = sum(not finite(vertex) for vertex in vertices)
        # Tessellation handles concave n-gons without a fan crossing outside
        # the face. Open shells remain valid unless a criterion says otherwise.
        for polygon in polygons:
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                key = tuple(sorted((a, b)))
                usage[key] = usage.get(key, 0) + 1
            area = 0.0
            coordinates = [vertices[index] for index in polygon]
            if len(polygon) >= 3 and finite(value for point in coordinates for value in point):
                for a, b, c in tessellate_polygon([coordinates]):
                    # Blender releases return either vector triples or indices.
                    if isinstance(a, int):
                        a, b, c = coordinates[a], coordinates[b], coordinates[c]
                    area += (b - a).cross(c - a).length * 0.5
            if area * self.mm * self.mm <= epsilon_mm2:
                zero_area += 1
        counts = list(usage.values())
        used_vertices = {index for edge in edges for index in edge}
        return {
            "vertices": len(vertices), "edges": len(edges), "faces": len(polygons),
            "boundary_edges": sum(count == 1 for count in counts),
            "overfull_edges": sum(count > 2 for count in counts),
            "wire_edges": sum(count == 0 for count in counts),
            "nonmanifold_edges": sum(count != 2 for count in counts),
            "loose_vertices": len(vertices) - len(used_vertices),
            "zero_area_faces": zero_area, "nonfinite_vertices": nonfinite_vertices,
            "zero_area_epsilon_mm2": epsilon_mm2,
            "area_measurement": "world-space tessellated polygon area",
        }

    def transform(self, obj, depsgraph):
        evaluated = obj.evaluated_get(depsgraph)
        matrix = evaluated.matrix_world
        location, rotation, scale = matrix.decompose()
        values = matrix_values(matrix) + list(obj.location) + list(obj.scale)
        values += list(obj.rotation_quaternion if obj.rotation_mode == "QUATERNION"
                       else obj.rotation_axis_angle if obj.rotation_mode == "AXIS_ANGLE"
                       else obj.rotation_euler)
        return {
            "finite": finite(values), "matrix_world": [list(row) for row in matrix],
            "location_mm": [value * self.mm for value in location],
            "rotation_deg": [math.degrees(value) for value in rotation.to_euler("XYZ")],
            "scale": list(scale),
        }

    def compare_vector(self, label, actual, criterion, tolerance_key):
        expected = criterion["expected"]
        tolerance = criterion[tolerance_key]
        tolerance = [tolerance] * 3 if isinstance(tolerance, (int, float)) else tolerance
        if len(expected) != 3 or len(tolerance) != 3:
            raise ValueError(label + " needs 3 expected values and 1 or 3 tolerances")
        if not finite(expected + tolerance) or any(value < 0 for value in tolerance):
            raise ValueError(label + " expected/tolerance must be finite; tolerance >= 0")
        passed = actual is not None and finite(actual) and all(
            abs(actual[i] - expected[i]) <= tolerance[i] for i in range(3))
        self.check(label, passed, actual, {"value": expected, "tolerance": tolerance})

    def target(self, spec):
        label = "target/" + spec["id"]
        reject_unknown(spec, {"id", "description", "frame", "objects", "collections",
                              "dimensions_mm", "topology", "finite_transforms"}, label)
        if "finite_transforms" in spec and not isinstance(spec["finite_transforms"], bool):
            raise ValueError("finite_transforms must be true or false")
        reject_unknown(spec.get("topology", {}), {"base", "evaluated"}, label + "/topology")
        if "frame" in spec:
            self.set_frame(spec["frame"])
        objects = self.select(spec, label)
        if spec.get("topology"):
            self.check(label + "/topology_mesh_scope", any(obj.type == "MESH" for obj in objects))
        depsgraph = bpy.context.evaluated_depsgraph_get()
        geometries = []
        records = []
        for obj in objects:
            transform = self.transform(obj, depsgraph)
            if spec.get("finite_transforms") is True:
                self.check(label + "/finite_transform/" + obj.name, transform["finite"])
            geometry = self.geometry(obj, depsgraph)
            geometries.append(geometry)
            record = {"name": obj.name, "type": obj.type, "transform": transform}
            if obj.type == "MESH":
                topology_spec = spec.get("topology", {})
                base = (
                    [obj.matrix_world @ vertex.co for vertex in obj.data.vertices],
                    [tuple(poly.vertices) for poly in obj.data.polygons],
                    [tuple(edge.vertices) for edge in obj.data.edges],
                )
                for mode, data in (("base", base), ("evaluated", geometry)):
                    criteria = topology_spec.get(mode, {})
                    epsilon = float(criteria.get("zero_area_epsilon_mm2", 1e-10))
                    if not math.isfinite(epsilon) or epsilon < 0:
                        raise ValueError("zero_area_epsilon_mm2 must be finite and >= 0")
                    stats = self.topology(*data, epsilon)
                    record[mode + "_topology"] = stats
                    for key, maximum in criteria.items():
                        if key == "zero_area_epsilon_mm2":
                            continue
                        if not key.startswith("max_") or key[4:] not in stats:
                            raise ValueError("unsupported topology criterion: " + key)
                        if not isinstance(maximum, (int, float)) or not math.isfinite(maximum) or maximum < 0:
                            raise ValueError(key + " must be a nonnegative number")
                        self.check(label + "/" + obj.name + "/" + mode + "/" + key,
                                   stats[key[4:]] <= maximum, stats[key[4:]], maximum)
            records.append(record)
        bounds = self.bounds(geometries)
        if "dimensions_mm" in spec:
            actual = bounds["dimensions_mm"] if bounds else None
            self.compare_vector(label + "/dimensions_mm", actual,
                                spec["dimensions_mm"], "tolerance_mm")
        self.info(label + "/topology_interpretation",
                  "Boundary or nonmanifold counts are observations. Only explicit maxima are acceptance criteria.")
        return {"id": spec["id"], "frame": self.scene.frame_current,
                "bounds": bounds, "objects": records}

    def render_paths(self):
        result = {}

        def walk(collection, allowed):
            allowed = allowed and not collection.hide_render
            for obj in collection.objects:
                result[obj.name] = result.get(obj.name, False) or allowed
            for child in collection.children:
                walk(child, allowed)

        walk(self.scene.collection, True)
        return result

    def pose(self, spec):
        label = "pose/" + spec["id"]
        reject_unknown(spec, {"id", "description", "frame", "objects", "collections",
                              "camera", "criteria"}, label)
        self.set_frame(spec["frame"])
        objects = self.select(spec, label)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        render_paths = self.render_paths()
        records = {}
        for obj in objects:
            transform = self.transform(obj, depsgraph)
            bounds = self.bounds([self.geometry(obj, depsgraph)])
            nonzero_scale = abs(obj.evaluated_get(depsgraph).matrix_world.determinant()) > 1e-18
            records[obj.name] = {
                "transform": transform, "bounds": bounds,
                "render_visible": bool(not obj.hide_render and render_paths.get(obj.name, False)
                                       and nonzero_scale),
                "viewport_visible": bool(obj.visible_get()),
                "hide_render": bool(obj.hide_render), "hide_viewport": bool(obj.hide_viewport),
                "visibility_definition": "object/collection render flags and nonzero world scale; no occlusion test",
            }
        for criteria in spec.get("criteria", []):
            reject_unknown(criteria, {"object", "visible", "finite_transform", "location_mm",
                                      "rotation_deg", "dimensions_mm"}, label + "/criteria")
            if "finite_transform" in criteria and not isinstance(criteria["finite_transform"], bool):
                raise ValueError("finite_transform must be true or false")
            name = criteria["object"]
            if name not in records:
                raise ValueError(label + ": criterion object must be explicitly selected: " + name)
            record = records[name]
            if "visible" in criteria:
                if not isinstance(criteria["visible"], bool):
                    raise ValueError("visible acceptance criterion must be true or false")
                self.check(label + "/" + name + "/visible",
                           record["render_visible"] == criteria["visible"],
                           record["render_visible"], criteria["visible"])
            for key, tolerance in (("location_mm", "tolerance_mm"),
                                   ("rotation_deg", "tolerance_deg"),
                                   ("dimensions_mm", "tolerance_mm")):
                if key in criteria:
                    value = record["bounds"].get(key) if key == "dimensions_mm" and record["bounds"] else record["transform"].get(key)
                    self.compare_vector(label + "/" + name + "/" + key, value,
                                        criteria[key], tolerance)
            if criteria.get("finite_transform") is True:
                self.check(label + "/" + name + "/finite_transform", record["transform"]["finite"])
        camera = None
        if "camera" in spec:
            obj = bpy.data.objects.get(spec["camera"])
            valid = obj is not None and obj.type == "CAMERA"
            self.check(label + "/camera_exists", valid, spec["camera"])
            if valid:
                camera = {"name": obj.name, "transform": self.transform(obj, depsgraph),
                          "type": obj.data.type, "lens_mm": obj.data.lens,
                          "ortho_scale_mm": obj.data.ortho_scale * self.mm,
                          "is_active": obj == self.scene.camera}
        return {"id": spec["id"], "frame": self.scene.frame_current,
                "objects": records, "camera": camera}

    def set_frame(self, frame):
        if not isinstance(frame, int) or isinstance(frame, bool):
            raise ValueError("frame must be an integer")
        self.scene.frame_set(frame)
        bpy.context.view_layer.update()

    def passage(self, spec):
        label = "passage/" + spec["id"]
        reject_unknown(spec, {"id", "description", "frame", "objects", "collections",
                              "reference_object", "unit", "samples", "max_hits"}, label)
        if "frame" in spec:
            self.set_frame(spec["frame"])
        objects = self.select(spec, label)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        trees = []
        for obj in objects:
            vertices, polygons, _ = self.geometry(obj, depsgraph)
            if vertices and polygons and finite(value for point in vertices for value in point):
                trees.append((obj.name, BVHTree.FromPolygons(vertices, polygons)))
        matrix = None
        if "reference_object" in spec:
            obj = bpy.data.objects.get(spec["reference_object"])
            if obj is None:
                raise ValueError(label + ": reference_object not found")
            matrix = obj.evaluated_get(depsgraph).matrix_world.copy()
        unit = spec.get("unit", "mm")
        if unit not in {"mm", "scene"}:
            raise ValueError("passage unit must be mm or scene")
        factor = 1.0 / self.mm if unit == "mm" else 1.0
        samples = spec["samples"]
        if not samples:
            raise ValueError(label + ": samples cannot be empty")
        results = []
        for index, sample in enumerate(samples):
            if len(sample["start"]) != 3 or len(sample["end"]) != 3 or not finite(sample["start"] + sample["end"]):
                raise ValueError(label + ": each start/end must contain 3 finite coordinates")
            start = Vector(sample["start"]) * factor
            end = Vector(sample["end"]) * factor
            if matrix is not None:
                start, end = matrix @ start, matrix @ end
            length = (end - start).length
            if length <= 1e-15:
                raise ValueError(label + ": zero-length sample")
            direction = (end - start) / length
            hits = []
            for name, tree in trees:
                position, normal, face_index, distance = tree.ray_cast(start, direction, length)
                if position is not None and distance <= length:
                    hits.append({"object": name, "position_mm": [value * self.mm for value in position],
                                 "normal_world": list(normal), "face_index": face_index,
                                 "distance_mm": distance * self.mm})
            hits.sort(key=lambda hit: hit["distance_mm"])
            results.append({"index": index,
                            "start_world_mm": [value * self.mm for value in start],
                            "end_world_mm": [value * self.mm for value in end],
                            "hit": bool(hits), "first_hit": hits[0] if hits else None,
                            "hits": hits})
        hit_count = sum(sample["hit"] for sample in results)
        if "max_hits" in spec:
            maximum = spec["max_hits"]
            if not isinstance(maximum, int) or maximum < 0:
                raise ValueError("max_hits must be a nonnegative integer")
            if not trees:
                raise ValueError(label + ": clearance criterion needs selected polygon surfaces")
            self.check(label + "/max_hits", hit_count <= maximum, hit_count, maximum)
        else:
            self.info(label + "/sampled_passage", "No clearance acceptance criterion supplied.")
        return {"id": spec["id"], "frame": self.scene.frame_current,
                "selected_objects": [obj.name for obj in objects], "hit_samples": hit_count,
                "sample_count": len(samples), "samples": results,
                "visibility_filter": "none; selected evaluated geometry includes render-hidden objects",
                "limitation": "Finite visual sample rays, first surface hit per selected object; not proof of continuous clearance or mechanical function."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if not os.path.isabs(args.output):
        parser.error("--output must be an absolute path")
    if args.config and not os.path.isabs(args.config):
        parser.error("--config must be an absolute path")
    scene = bpy.context.scene
    original_frame, original_subframe, original_camera = scene.frame_current, scene.frame_subframe, scene.camera
    auditor = Auditor(scene, bool(args.config))
    report = {"schema_version": VERSION, "blend_file": bpy.data.filepath,
              "blender_version": bpy.app.version_string, "configured": bool(args.config),
              "unit_scale_length": scene.unit_settings.scale_length,
              "initial_frame": original_frame, "targets": [], "poses": [], "passages": [],
              "errors": [], "read_only": "No .blend is saved; only this JSON is written."}
    try:
        if args.config:
            with open(args.config, encoding="utf-8-sig") as stream:
                config = json.load(stream)
            reject_unknown(config, {"schema_version", "description", "targets", "poses", "passages"}, "config")
            if config.get("schema_version") != VERSION:
                raise ValueError("config schema_version must be 1")
        else:
            config = {"targets": [{"id": "scene_inventory"}]}
        for section, method in (("targets", auditor.target), ("poses", auditor.pose),
                                ("passages", auditor.passage)):
            for spec in config.get(section, []):
                try:
                    report[section].append(method(spec))
                except Exception as error:
                    report["errors"].append({"section": section, "id": spec.get("id"),
                                             "error": str(error)})
    except Exception as error:
        report["errors"].append({"section": "config", "error": str(error)})
    finally:
        scene.frame_set(original_frame, subframe=original_subframe)
        scene.camera = original_camera
        bpy.context.view_layer.update()
        report["restored_frame"] = scene.frame_current
        report["restored_camera"] = scene.camera.name if scene.camera else None
    report["checks"] = auditor.checks
    report["acceptance_check_count"] = sum(check["status"] in {"PASS", "FAIL"} for check in auditor.checks)
    report["scope_note"] = "Acceptance applies only to listed criteria, objects, frames and sampled rays; INFO observations are not acceptance checks."
    statuses = {check["status"] for check in auditor.checks}
    report["status"] = "ERROR" if report["errors"] else "FAIL" if "FAIL" in statuses else "PASS" if "PASS" in statuses else "INFO"
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as stream:
        json.dump(clean_json(report), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print("ASSET_AUDIT " + report["status"] + " " + output)


if __name__ == "__main__":
    main()
