from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Sequence, Tuple

import numpy as np

from layout import LayoutGeometry, MaskPolygon

MAX_SHAPES = 50_000
MAX_POLYGON_VERTICES = 500_000
# Bound quadratic topology validation independently of the asset-wide budget.
MAX_SHAPE_POINTS = 1024
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class MaskAssetError(ValueError):
    def __init__(self, code: str, error: str, *, params: Mapping[str, Any] | None = None,
                 status: int = 400, detail: str | None = None) -> None:
        super().__init__(error)
        self.code = code
        self.error = error
        self.params = dict(params or {})
        self.status = int(status)
        self.detail = detail

    def envelope(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "code": self.code, "params": self.params, "error": self.error}
        if self.detail:
            out["detail"] = self.detail
        return out


def validate_asset_id(value: Any, path: str = "id") -> str:
    asset_id = str(value).strip()
    if not _ID_RE.fullmatch(asset_id):
        raise MaskAssetError("invalid_mask_asset", "Invalid mask asset id", params={"path": path})
    return asset_id


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool):
        raise MaskAssetError("invalid_mask_asset", f"{path} must be finite", params={"path": path})
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise MaskAssetError("invalid_mask_asset", f"{path} must be finite", params={"path": path})
    if not math.isfinite(number):
        raise MaskAssetError("invalid_mask_asset", f"{path} must be finite", params={"path": path})
    return number


def _positive(value: Any, path: str) -> float:
    number = _finite(value, path)
    if number <= 0:
        raise MaskAssetError("invalid_mask_asset", f"{path} must be positive", params={"path": path})
    return number


def _integer(value: Any, path: str, minimum: int = 0) -> int:
    number = _finite(value, path)
    if not number.is_integer() or number < minimum:
        raise MaskAssetError("invalid_mask_asset", f"{path} must be an integer >= {minimum}", params={"path": path})
    return int(number)


@dataclass(frozen=True)
class MaskLayer:
    id: str
    layer: int
    datatype: int
    name: str
    visible: bool = True

    def to_mapping(self) -> dict[str, Any]:
        return {"id": self.id, "layer": self.layer, "datatype": self.datatype,
                "name": self.name, "visible": self.visible}


@dataclass(frozen=True)
class MaskShape:
    id: str
    type: str
    layer_id: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "layer_id": self.layer_id, **dict(self.data)}


@dataclass(frozen=True)
class MaskAsset:
    version: int
    id: str
    revision: int
    name: str
    coordinate_unit: str
    bounds_nm: Tuple[float, float, float, float]
    layers: Tuple[MaskLayer, ...]
    shapes: Tuple[MaskShape, ...]
    source: Mapping[str, Any]
    sha256: str = ""

    def to_mapping(self) -> dict[str, Any]:
        out = {
            "version": self.version, "id": self.id, "revision": self.revision,
            "name": self.name, "coordinate_unit": self.coordinate_unit,
            "bounds_nm": list(self.bounds_nm),
            "layers": [item.to_mapping() for item in self.layers],
            "shapes": [item.to_mapping() for item in self.shapes],
            "source": dict(self.source),
        }
        if self.sha256:
            out["sha256"] = self.sha256
        return out

    def to_polygons(self) -> tuple[MaskPolygon, ...]:
        by_id = {item.id: item for item in self.layers}
        polygons: list[MaskPolygon] = []
        for shape in self.shapes:
            layer = by_id[shape.layer_id]
            for points in _shape_polygons(shape):
                polygons.append(MaskPolygon(points=points, layer=layer.layer, datatype=layer.datatype))
        return tuple(polygons)


@dataclass(frozen=True)
class MaskAssetCandidate:
    version: int
    id: str
    name: str
    coordinate_unit: str
    bounds_nm: Tuple[float, float, float, float]
    layers: Tuple[MaskLayer, ...]
    shapes: Tuple[MaskShape, ...]
    source: Mapping[str, Any]

    def with_revision(self, revision: int, *, sha256: str = "") -> MaskAsset:
        return MaskAsset(self.version, self.id, int(revision), self.name, self.coordinate_unit,
                         self.bounds_nm, self.layers, self.shapes, self.source, sha256)

    def to_mapping(self) -> dict[str, Any]:
        return self.with_revision(0).to_mapping()


def parse_candidate(payload: Mapping[str, Any]) -> MaskAssetCandidate:
    if not isinstance(payload, Mapping):
        raise MaskAssetError("invalid_mask_asset", "Mask asset must be an object")
    if _integer(payload.get("version"), "version", 1) != 1:
        raise MaskAssetError("unsupported_mask_asset_version", "Only mask asset version 1 is supported")
    asset_id = validate_asset_id(payload.get("id", ""))
    if payload.get("coordinate_unit") != "nm":
        raise MaskAssetError("invalid_coordinate_unit", "coordinate_unit must be nm", params={"coordinate_unit": payload.get("coordinate_unit")})
    raw_bounds = payload.get("bounds_nm")
    if not isinstance(raw_bounds, Sequence) or isinstance(raw_bounds, (str, bytes)) or len(raw_bounds) != 4:
        raise MaskAssetError("invalid_mask_asset", "bounds_nm must have four finite coordinates")
    bounds = tuple(_finite(value, f"bounds_nm[{index}]") for index, value in enumerate(raw_bounds))
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise MaskAssetError("invalid_mask_asset", "bounds_nm must have positive area")
    raw_layers = payload.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        raise MaskAssetError("invalid_mask_asset", "layers must be a non-empty array")
    layers: list[MaskLayer] = []
    layer_ids: set[str] = set()
    for index, raw in enumerate(raw_layers):
        if not isinstance(raw, Mapping):
            raise MaskAssetError("invalid_mask_asset", "layer must be an object")
        layer_id = str(raw.get("id", "")).strip()
        if not layer_id or layer_id in layer_ids:
            raise MaskAssetError("invalid_mask_asset", "Layer ids must be unique", params={"path": f"layers[{index}].id"})
        layer_ids.add(layer_id)
        layers.append(MaskLayer(layer_id, _integer(raw.get("layer"), f"layers[{index}].layer"),
                                _integer(raw.get("datatype", 0), f"layers[{index}].datatype"),
                                str(raw.get("name", layer_id)), bool(raw.get("visible", True))))
    raw_shapes = payload.get("shapes")
    if not isinstance(raw_shapes, list):
        raise MaskAssetError("invalid_mask_asset", "shapes must be an array")
    if len(raw_shapes) > MAX_SHAPES:
        raise MaskAssetError("mask_asset_budget_exceeded", "Mask asset has too many shapes", status=413,
                             params={"limit": MAX_SHAPES})
    shapes: list[MaskShape] = []
    shape_ids: set[str] = set()
    vertex_count = 0
    for index, raw in enumerate(raw_shapes):
        if not isinstance(raw, Mapping):
            raise MaskAssetError("invalid_mask_asset", "shape must be an object")
        shape_id = str(raw.get("id", "")).strip()
        if not shape_id or shape_id in shape_ids:
            raise MaskAssetError("invalid_mask_asset", "Shape ids must be unique", params={"path": f"shapes[{index}].id"})
        shape_ids.add(shape_id)
        layer_id = str(raw.get("layer_id", ""))
        if layer_id not in layer_ids:
            raise MaskAssetError("invalid_mask_asset", "Shape references an unknown layer", params={"path": f"shapes[{index}].layer_id"})
        kind = str(raw.get("type", "")).lower()
        if kind in {"polygon", "line"}:
            raw_points = raw.get("points_nm")
            if isinstance(raw_points, list):
                count = len(raw_points)
                limit = MAX_SHAPE_POINTS + (kind == "polygon")
                estimate = max(0, count - 1) if kind == "polygon" else max(0, count - 1) * 4 + max(0, count - 2) * 64
                if count > limit or vertex_count + estimate > MAX_POLYGON_VERTICES:
                    raise MaskAssetError("mask_asset_budget_exceeded", "Shape exceeds vertex budget", status=413,
                                         params={"limit": MAX_SHAPE_POINTS if count > limit else MAX_POLYGON_VERTICES})
        if kind == "polygon":
            raw_points = raw.get("points_nm")
            if isinstance(raw_points, list) and vertex_count + max(0, len(raw_points) - 1) > MAX_POLYGON_VERTICES:
                raise MaskAssetError("mask_asset_budget_exceeded", "Mask asset has too many polygon vertices", status=413,
                                     params={"limit": MAX_POLYGON_VERTICES})
        data = _validate_shape_data(kind, raw, index)
        shape = MaskShape(shape_id, kind, layer_id, MappingProxyType(data))
        shape_polygons = _shape_polygons(shape)
        vertex_count += sum(points.shape[0] for points in shape_polygons)
        if vertex_count > MAX_POLYGON_VERTICES:
            raise MaskAssetError("mask_asset_budget_exceeded", "Mask asset has too many polygon vertices", status=413,
                                 params={"limit": MAX_POLYGON_VERTICES})
        for points in shape_polygons:
            if np.any(points[:, 0] < bounds[0]) or np.any(points[:, 0] > bounds[2]) or np.any(points[:, 1] < bounds[1]) or np.any(points[:, 1] > bounds[3]):
                raise MaskAssetError("mask_asset_out_of_bounds", "Shape exceeds bounds", params={"shape_id": shape_id})
        shapes.append(shape)
    source = payload.get("source", {"kind": "editor"})
    if not isinstance(source, Mapping):
        raise MaskAssetError("invalid_mask_asset", "source must be an object")
    return MaskAssetCandidate(1, asset_id, str(payload.get("name", asset_id)), "nm", bounds,
                              tuple(layers), tuple(shapes), MappingProxyType(dict(source)))


def _points(raw: Any, path: str) -> list[list[float]]:
    if not isinstance(raw, list):
        raise MaskAssetError("invalid_mask_asset", f"{path} must be an array")
    out = []
    for index, point in enumerate(raw):
        if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) != 2:
            raise MaskAssetError("invalid_mask_asset", f"{path}[{index}] must be [x,y]")
        out.append([_finite(point[0], f"{path}[{index}][0]"), _finite(point[1], f"{path}[{index}][1]")])
    return out


def _validate_shape_data(kind: str, raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    prefix = f"shapes[{index}]"
    if kind == "rectangle":
        return {"x_nm": _finite(raw.get("x_nm"), prefix + ".x_nm"),
                "y_nm": _finite(raw.get("y_nm"), prefix + ".y_nm"),
                "width_nm": _positive(raw.get("width_nm"), prefix + ".width_nm"),
                "height_nm": _positive(raw.get("height_nm"), prefix + ".height_nm"),
                "rotation_deg": _finite(raw.get("rotation_deg", 0), prefix + ".rotation_deg")}
    if kind in {"circle", "hole"}:
        return {"cx_nm": _finite(raw.get("cx_nm"), prefix + ".cx_nm"),
                "cy_nm": _finite(raw.get("cy_nm"), prefix + ".cy_nm"),
                "radius_nm": _positive(raw.get("radius_nm"), prefix + ".radius_nm")}
    if kind == "line":
        points = _points(raw.get("points_nm"), prefix + ".points_nm")
        if len(points) < 2:
            raise MaskAssetError("invalid_mask_asset", "Line needs at least two points")
        return {"points_nm": points, "width_nm": _positive(raw.get("width_nm"), prefix + ".width_nm")}
    if kind == "polygon":
        points = _points(raw.get("points_nm"), prefix + ".points_nm")
        if len(points) < 4 or points[0] != points[-1]:
            raise MaskAssetError("invalid_mask_asset", "Polygon must be explicitly closed")
        if _self_intersects(np.asarray(points[:-1], dtype=float)):
            raise MaskAssetError("invalid_mask_asset", "Polygon must not self-intersect")
        return {"points_nm": points}
    raise MaskAssetError("invalid_mask_asset", "Unknown shape type", params={"type": kind})


def _shape_polygons(shape: MaskShape) -> tuple[np.ndarray, ...]:
    data = shape.data
    if shape.type == "rectangle":
        x, y = data["x_nm"], data["y_nm"]
        w, h = data["width_nm"], data["height_nm"]
        points = np.asarray([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=float)
        angle = math.radians(data["rotation_deg"])
        if angle:
            center = np.asarray([x + w / 2.0, y + h / 2.0])
            rotation = np.asarray([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
            points = (points - center) @ rotation.T + center
        return (points,)
    if shape.type in {"circle", "hole"}:
        angles = np.linspace(0.0, math.tau, 64, endpoint=False)
        return (np.column_stack((data["cx_nm"] + data["radius_nm"] * np.cos(angles),
                                 data["cy_nm"] + data["radius_nm"] * np.sin(angles))),)
    if shape.type == "polygon":
        return (np.asarray(data["points_nm"][:-1], dtype=float),)
    points = np.asarray(data["points_nm"], dtype=float)
    half = data["width_nm"] / 2.0
    polys = []
    for start, end in zip(points[:-1], points[1:]):
        delta = end - start
        length = float(np.linalg.norm(delta))
        if length <= 0:
            raise MaskAssetError("invalid_mask_asset", "Line segments must have positive length")
        normal = np.asarray([-delta[1], delta[0]]) / length * half
        polys.append(np.asarray([start + normal, end + normal, end - normal, start - normal]))
    # Round internal joins fill the outside of a bend; segment contours are unioned.
    angles = np.linspace(0.0, math.tau, 64, endpoint=False)
    offsets = np.column_stack((np.cos(angles), np.sin(angles))) * half
    polys.extend(center + offsets for center in points[1:-1])
    return tuple(polys)


def _self_intersects(points: np.ndarray) -> bool:
    def orient(a, b, c):
        ab = b - a
        ac = c - a
        return float(ab[0] * ac[1] - ab[1] * ac[0])
    count = len(points)
    if len({tuple(point) for point in points}) != count:
        return True
    relative = points - points[0]
    if float(np.sum(relative[:, 0] * np.roll(relative[:, 1], -1)
                    - relative[:, 1] * np.roll(relative[:, 0], -1))) == 0:
        return True
    def on_segment(a, b, c):
        return orient(a, b, c) == 0 and np.all(c >= np.minimum(a, b)) and np.all(c <= np.maximum(a, b))
    for i in range(count):
        a, b = points[i], points[(i + 1) % count]
        c = points[(i + 2) % count]
        if orient(a, b, c) == 0 and float(np.dot(a - b, c - b)) > 0:
            return True  # Adjacent collinear edges double back and overlap.
        for j in range(i + 1, count):
            if j in {i, (i + 1) % count} or (j + 1) % count in {i, (i + 1) % count}:
                continue
            c, d = points[j], points[(j + 1) % count]
            if np.any(np.maximum(a, b) < np.minimum(c, d)) or np.any(np.maximum(c, d) < np.minimum(a, b)):
                continue
            if on_segment(a, b, c) or on_segment(a, b, d) or on_segment(c, d, a) or on_segment(c, d, b):
                return True
            if orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0:
                return True
    return False


def to_layout_geometry(asset: MaskAsset | MaskAssetCandidate) -> LayoutGeometry:
    concrete = asset if isinstance(asset, MaskAsset) else asset.with_revision(0)
    return LayoutGeometry.from_polygons(concrete.to_polygons())
