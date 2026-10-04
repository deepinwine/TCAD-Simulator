from __future__ import annotations

import json
from functools import wraps
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from layout import LayoutAdapter, LayoutGeometry, MaskPolygon

from .model import MaskAsset, MaskAssetError, _shape_polygons, parse_candidate
from .store import MaskAssetStore


def _safe_operation(code: str, message: str, status: int = 500):
    def decorate(operation):
        @wraps(operation)
        def call(*args, **kwargs):
            try:
                return operation(*args, **kwargs)
            except MaskAssetError:
                raise
            except (ImportError, ModuleNotFoundError) as exc:
                raise MaskAssetError('dependency_missing', 'GDS support requires gdstk',
                                     params={'dependency': 'gdstk'}) from exc
            except Exception as exc:
                if isinstance(exc, ValueError) and 'budget' in str(exc).lower():
                    raise MaskAssetError('mask_asset_budget_exceeded', 'Mask geometry exceeds processing budget', status=413) from exc
                raise MaskAssetError(code, message, status=status) from exc
        return call
    return decorate


class MaskAssetService:
    def __init__(self, store: MaskAssetStore, *, adapter: Any | None = None) -> None:
        self.store = store
        self._adapter = adapter

    def _layout_adapter(self):
        if self._adapter is not None:
            return self._adapter
        try:
            return LayoutAdapter()
        except (ImportError, ModuleNotFoundError) as exc:
            raise MaskAssetError("dependency_missing", "GDS support requires gdstk",
                                 params={"dependency": "gdstk"}, status=400) from exc

    def _raster_adapter(self):
        return self._adapter if self._adapter is not None else LayoutAdapter.normalized()

    @_safe_operation('mask_asset_apply_failed', 'Mask asset save failed')
    def save_candidate(self, payload: Mapping[str, Any]) -> MaskAsset:
        candidate = parse_candidate(payload)
        revision = self.store.current_revision(candidate.id) + 1
        asset = candidate.with_revision(revision)
        # JSON editing and execution never require the optional GDS dependency.
        self._rasterize_asset(asset, shape=(64, 64), bounds=asset.bounds_nm)
        return self.store.publish(asset)

    @_safe_operation('mask_asset_store_failed', 'Mask asset read failed')
    def get(self, asset_id: str, revision: int | None = None) -> MaskAsset:
        return self.store.get(asset_id, revision)

    @_safe_operation('mask_asset_store_failed', 'Mask asset listing failed')
    def list(self) -> list[dict[str, Any]]:
        return self.store.list()

    @_safe_operation('mask_asset_store_failed', 'Mask asset deletion failed')
    def delete(self, asset_id: str, *, references: Iterable[Mapping[str, Any]] = ()) -> None:
        refs = [dict(item) for item in references]
        if refs:
            raise MaskAssetError("mask_asset_in_use", "Mask asset is referenced by a recipe", status=409,
                                 params={"references": refs})
        self.store.delete(asset_id)

    def rasterize(self, asset_id: str, revision: int, *, shape, bounds=None):
        asset = self.get(asset_id, revision)
        return self._rasterize_asset(asset, shape=shape,
                                     bounds=asset.bounds_nm if bounds is None else bounds), asset

    @_safe_operation('mask_asset_apply_failed', 'Mask asset rasterization failed')
    def _rasterize_asset(self, asset: MaskAsset, *, shape, bounds):
        """Union ordinary contours, subtract holes within their editable layer.

        LayoutAdapter retains its public even-odd contract. Each call here contains
        one contour, preserving asset polarity before layers are finally unioned.
        """
        adapter = self._raster_adapter()
        empty = adapter.rasterize(LayoutGeometry.from_polygons(()), shape=shape, bounds=bounds)
        result = np.zeros_like(empty, dtype=bool)
        by_layer = {layer.id: [] for layer in asset.layers}
        for item in asset.shapes:
            by_layer[item.layer_id].append(item)
        for layer in asset.layers:
            positive = np.zeros_like(result)
            negative = np.zeros_like(result)
            for item in by_layer[layer.id]:
                target = negative if item.type == "hole" else positive
                for points in _shape_polygons(item):
                    geometry = LayoutGeometry.from_polygons((MaskPolygon(points, layer.layer, layer.datatype),))
                    target |= adapter.rasterize(geometry, shape=shape, bounds=bounds)
            result |= positive & ~negative
        return result

    def import_json(self, data: str | bytes) -> MaskAsset:
        try:
            payload = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        except Exception as exc:
            raise MaskAssetError("invalid_mask_asset", "Mask asset JSON is invalid") from exc
        return self.save_candidate(payload)

    def export_json(self, asset_id: str, revision: int) -> bytes:
        return json.dumps(self.get(asset_id, revision).to_mapping(), ensure_ascii=False, indent=2).encode("utf-8")

    @_safe_operation('invalid_mask_asset_import', 'Mask asset layout import failed', 400)
    def import_gds(self, path: Path, *, asset_id: str, name: str) -> MaskAsset:
        adapter = self._layout_adapter()
        if hasattr(adapter, "read_with_metadata"):
            geometry, metadata = adapter.read_with_metadata(path)
        else:
            geometry, metadata = adapter.read(path), {}
        layers = sorted(geometry.layers())
        payload = {
            "version": 1, "id": asset_id, "name": name, "coordinate_unit": "nm",
            "bounds_nm": list(geometry.bounds),
            "layers": [{"id": f"{layer}/{datatype}", "layer": layer, "datatype": datatype,
                        "name": f"{layer}/{datatype}", "visible": True} for layer, datatype in layers],
            "shapes": [{"id": f"shape_{index + 1}", "type": "polygon",
                        "layer_id": f"{polygon.layer}/{polygon.datatype}",
                        "points_nm": [*polygon.points.tolist(), polygon.points[0].tolist()]}
                       for index, polygon in enumerate(geometry.polygons)],
            "source": {"kind": "gds", "filename": Path(path).name, **metadata},
        }
        return self.save_candidate(payload)

    @_safe_operation('mask_asset_export_failed', 'Mask asset layout export failed')
    def export_gds(self, asset_id: str, revision: int, path: Path) -> None:
        asset = self.get(asset_id, revision)
        adapter = self._layout_adapter()
        output = []
        by_layer = {layer.id: [] for layer in asset.layers}
        for shape in asset.shapes:
            by_layer[shape.layer_id].append(shape)
        for layer in asset.layers:
            positive, negative = [], []
            for shape in by_layer[layer.id]:
                target = negative if shape.type == "hole" else positive
                target.extend(MaskPolygon(points, layer.layer, layer.datatype)
                              for points in _shape_polygons(shape))
            if not positive:
                continue
            geometry = LayoutGeometry.from_polygons(positive)
            empty = LayoutGeometry.from_polygons(())
            if len(positive) > 1:
                geometry = adapter.boolean(geometry, empty, 'or', layer=layer.layer, datatype=layer.datatype)
            if negative:
                geometry = adapter.boolean(geometry, LayoutGeometry.from_polygons(negative), 'sub',
                                           layer=layer.layer, datatype=layer.datatype)
                geometry = adapter.fracture(geometry)
            output.extend(geometry.polygons)
        adapter.write(LayoutGeometry.from_polygons(output), path, name=asset.name or "MASK")
