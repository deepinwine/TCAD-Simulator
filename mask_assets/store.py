from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .model import MaskAsset, MaskAssetError, parse_candidate, validate_asset_id


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _content_bytes(asset: MaskAsset) -> bytes:
    payload = asset.to_mapping()
    payload.pop("sha256", None)
    return _json_bytes(payload)


class MaskAssetStore:
    def __init__(self, session_root: Path) -> None:
        self.root = Path(session_root) / "mask_assets"

    def _asset_dir(self, asset_id: str) -> Path:
        return self.root / validate_asset_id(asset_id)

    def _manifest_path(self, asset_id: str) -> Path:
        return self._asset_dir(asset_id) / "manifest.json"

    def _revision_path(self, asset_id: str, revision: int) -> Path:
        return self._asset_dir(asset_id) / "revisions" / f"{int(revision)}.json"

    def current_revision(self, asset_id: str) -> int:
        path = self._manifest_path(asset_id)
        if not path.exists():
            return 0
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("current_revision", 0)
            return int(value)
        except Exception as exc:
            raise MaskAssetError("mask_asset_store_corrupt", "Mask asset manifest is invalid", status=500) from exc

    def publish(self, asset: MaskAsset) -> MaskAsset:
        asset_dir = self._asset_dir(asset.id)
        revisions = asset_dir / "revisions"
        revisions.mkdir(parents=True, exist_ok=True)
        revision_path = self._revision_path(asset.id, asset.revision)
        manifest_path = self._manifest_path(asset.id)
        if revision_path.exists():
            raise MaskAssetError("mask_asset_revision_exists", "Mask asset revision already exists", status=409)
        digest = hashlib.sha256(_content_bytes(asset)).hexdigest()
        asset = MaskAsset(asset.version, asset.id, asset.revision, asset.name, asset.coordinate_unit,
                          asset.bounds_nm, asset.layers, asset.shapes, asset.source, digest)
        revision_data = _json_bytes(asset.to_mapping())
        manifest_data = _json_bytes({"version": 1, "id": asset.id, "name": asset.name,
                                     "current_revision": asset.revision, "sha256": asset.sha256})
        rev_tmp = manifest_tmp = None
        try:
            fd, rev_name = tempfile.mkstemp(prefix=".revision-", suffix=".tmp", dir=revisions)
            rev_tmp = Path(rev_name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(revision_data); handle.flush(); os.fsync(handle.fileno())
            fd, manifest_name = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=asset_dir)
            manifest_tmp = Path(manifest_name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(manifest_data); handle.flush(); os.fsync(handle.fileno())
            os.replace(rev_tmp, revision_path)
            try:
                os.replace(manifest_tmp, manifest_path)
            except Exception:
                revision_path.unlink(missing_ok=True)
                raise
            return asset
        finally:
            if rev_tmp is not None: rev_tmp.unlink(missing_ok=True)
            if manifest_tmp is not None: manifest_tmp.unlink(missing_ok=True)

    def rollback_publish(self, asset_id: str, revision: int, previous_manifest: bytes | None) -> None:
        self._revision_path(asset_id, revision).unlink(missing_ok=True)
        manifest = self._manifest_path(asset_id)
        if previous_manifest is None:
            manifest.unlink(missing_ok=True)
            return
        manifest.parent.mkdir(parents=True, exist_ok=True)
        tmp = manifest.with_suffix(".rollback.tmp")
        tmp.write_bytes(previous_manifest)
        os.replace(tmp, manifest)

    def manifest_bytes(self, asset_id: str) -> bytes | None:
        path = self._manifest_path(asset_id)
        return path.read_bytes() if path.exists() else None

    def get(self, asset_id: str, revision: int | None = None) -> MaskAsset:
        selected = self.current_revision(asset_id) if revision is None else int(revision)
        path = self._revision_path(asset_id, selected)
        if selected <= 0 or not path.exists():
            raise MaskAssetError("mask_asset_not_found", "Mask asset revision was not found", status=404,
                                 params={"id": asset_id, "revision": selected})
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidate = parse_candidate(payload)
        asset = candidate.with_revision(selected, sha256=str(payload.get("sha256", "")))
        expected = hashlib.sha256(_content_bytes(asset)).hexdigest()
        if not asset.sha256 or asset.sha256 != expected:
            raise MaskAssetError("mask_asset_store_corrupt", "Mask asset revision hash is invalid", status=500,
                                 params={"id": asset_id, "revision": selected})
        return asset

    def list(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        out = []
        for manifest in sorted(self.root.glob("*/manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                out.append({"id": str(data["id"]), "name": str(data.get("name", data["id"])),
                            "revision": int(data["current_revision"]), "sha256": str(data.get("sha256", ""))})
            except Exception:
                continue
        return out

    def delete(self, asset_id: str) -> None:
        asset_dir = self._asset_dir(asset_id)
        if not asset_dir.exists():
            raise MaskAssetError("mask_asset_not_found", "Mask asset was not found", status=404, params={"id": asset_id})
        for path in sorted(asset_dir.rglob("*"), reverse=True):
            if path.is_file(): path.unlink()
            elif path.is_dir(): path.rmdir()
        asset_dir.rmdir()
