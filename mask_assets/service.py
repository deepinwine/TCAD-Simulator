from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from layout import LayoutAdapter

from .model import MaskAsset, MaskAssetError, parse_candidate, to_layout_geometry
from .store import MaskAssetStore


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

    def save_candidate(self, payload: Mapping[str, Any]) -> MaskAsset:
        candidate = parse_candidate(payload)
        revision = self.store.current_revision(candidate.id) + 1
        asset = candidate.with_revision(revision)
        geometry = to_layout_geometry(asset)
        # JSON editing and execution never require the optional GDS dependency.
        self._raster_adapter().rasterize(geometry, shape=(64, 64), bounds=asset.bounds_nm)
        return self.store.publish(asset)

    def get(self, asset_id: str, revision: int | None = None) -> MaskAsset:
        return self.store.get(asset_id, revision)

    def list(self) -> list[dict[str, Any]]:
        return self.store.list()

    def delete(self, asset_id: str, *, references: Iterable[Mapping[str, Any]] = ()) -> None:
        refs = [dict(item) for item in references]
        if refs:
            raise MaskAssetError("mask_asset_in_use", "Mask asset is referenced by a recipe", status=409,
                                 params={"references": refs})
        self.store.delete(asset_id)

    def rasterize(self, asset_id: str, revision: int, *, shape, bounds=None):
        asset = self.get(asset_id, revision)
        geometry = to_layout_geometry(asset)
        return self._raster_adapter().rasterize(
            geometry,
            shape=shape,
            bounds=asset.bounds_nm if bounds is None else bounds,
        ), asset

    def import_json(self, data: str | bytes) -> MaskAsset:
        try:
            payload = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        except Exception as exc:
            raise MaskAssetError("invalid_mask_asset", "Mask asset JSON is invalid") from exc
        return self.save_candidate(payload)

    def export_json(self, asset_id: str, revision: int) -> bytes:
        return json.dumps(self.get(asset_id, revision).to_mapping(), ensure_ascii=False, indent=2).encode("utf-8")

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

    def export_gds(self, asset_id: str, revision: int, path: Path) -> None:
        asset = self.get(asset_id, revision)
        self._layout_adapter().write(to_layout_geometry(asset), path, name=asset.name or "MASK")
