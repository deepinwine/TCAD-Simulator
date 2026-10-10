"""Revision-local display data derived only from current canonical voxels.

This is a presentation cache, not another GeometryScene or execution backend.
No model writes, step execution, timeline replay, or persistence occur here.
"""
import base64
import copy
import io

import numpy as np


class DisplayDataError(ValueError):
    def __init__(self, message, code='display_unavailable', status=400):
        super().__init__(message)
        self.code = code
        self.status = status


class DisplayGeometry:
    def __init__(self, *, max_groups=256, max_triangles=1000000,
                 max_cache_bytes=128 * 1024 * 1024, max_scan_voxels=128 * 1024 * 1024,
                 max_workspace_bytes=256 * 1024 * 1024, max_slice_bytes=32 * 1024 * 1024):
        self.max_groups = max_groups
        self.max_triangles = max_triangles
        self.max_cache_bytes = max_cache_bytes
        self.max_scan_voxels = max_scan_voxels
        self.max_workspace_bytes = max_workspace_bytes
        self.max_slice_bytes = max_slice_bytes
        self._revision = None
        self._manifest = None
        self._meshes = {}
        self._model = None

    @staticmethod
    def _check_revision(current, requested):
        if requested is not None and requested != current:
            raise DisplayDataError('Structure display revision mismatch', 'revision_mismatch', 409)

    def _prepare(self, model, revision):
        if self._model is model and self._revision == revision:
            return
        # Drop the previous revision before preparing, including on failure.
        self._model, self._revision = model, revision
        self._meshes = {}
        grid = model.grid
        source = model.display_provenance
        manifest = {
            'revision': int(revision), 'available': True,
            'domain': {'grid_shape': list(grid.shape), 'voxel_size_nm': float(model.voxel_size_nm),
                       'bounds_um': {'min': [-model.voxel_size_nm / 2000] * 3,
                                     'max': [(n - .5) * model.voxel_size_nm / 1000 for n in grid.shape]}},
            'owner_step_ids': {str(k): v for k, v in source.step_ids.items()},
            'groups': [], 'entity_counts': {}, 'unavailable_reasons': [], 'cache_bytes': 0,
            'budgets': {'groups': self.max_groups, 'triangles': self.max_triangles,
                        'cache_bytes': self.max_cache_bytes, 'scan_voxels': self.max_scan_voxels,
                        'workspace_bytes': self.max_workspace_bytes, 'slice_bytes': self.max_slice_bytes},
        }
        self._manifest = manifest
        try:
            # Covers packed keys, temporary uint64 owners and unique/sort work.
            if grid.size > self.max_scan_voxels or grid.size * 40 > self.max_workspace_bytes:
                raise DisplayDataError('Structure display scan budget exceeded', 'display_budget_exceeded', 413)
            owners = source.owners
            if owners is not None and (owners.shape != grid.shape or owners.dtype != np.uint32):
                raise DisplayDataError('Invalid display provenance')
            # Packing avoids huge Python tuple lists; 0 material is never an entity.
            keys = grid.astype(np.uint64)
            if owners is not None:
                keys |= owners.astype(np.uint64) << np.uint64(16)
            keys[grid == 0] = 0
            unique, counts = np.unique(keys, return_counts=True)
            present = [(int(k >> np.uint64(16)), int(k & np.uint64(65535)), int(n))
                       for k, n in zip(unique, counts) if k != 0]
            if len(present) > self.max_groups or grid.size * (len(present) + 1) > self.max_scan_voxels:
                raise DisplayDataError('Structure display group/scan budget exceeded', 'display_budget_exceeded', 413)
            for owner, mat, count in present:
                manifest['entity_counts'][str(owner)] = manifest['entity_counts'].get(str(owner), 0) + count
            if any(owner == 0 for owner, _, _ in present):
                manifest['unavailable_reasons'].append('unknown_provenance')
            import tcad_simulator as tcad
            total_triangles, cache_bytes = 0, 0
            groups, meshes = [], {}
            for owner, mat, count in present:
                # Codec upper bound: three unshared vertices (pos+normal) and indices.
                remaining = min(self.max_triangles - total_triangles,
                                (self.max_cache_bytes - cache_bytes - 24) // 84)
                try:
                    verts, faces = tcad.marching_cubes(
                        keys == ((owner << 16) | mat), .5, strict_voxels=True,
                        spacing=(model.voxel_size_nm / 1000,) * 3, triangle_limit=remaining)
                except ValueError as exc:
                    raise DisplayDataError(str(exc), 'display_budget_exceeded', 413) from exc
                triangles = verts[faces]
                output = io.BytesIO()
                model._write_tcad_geom(output, triangles, weld_tolerance_um=model.voxel_size_nm / 1000000)
                data = output.getvalue()
                if not data:
                    raise DisplayDataError('Display mesh preparation produced no geometry')
                total_triangles += len(faces)
                cache_bytes += len(data)
                meshes[(owner, mat)] = data
                groups.append({'owner_id': owner, 'mat_id': mat,
                               'step_id': source.step_ids.get(owner) if owner else None,
                               'voxel_count': count, 'tri_count': len(faces), 'bytes': len(data),
                               'bbox': {'min': verts.min(0).tolist(), 'max': verts.max(0).tolist()}})
            self._meshes = meshes
            manifest['groups'] = groups
            manifest['cache_bytes'] = cache_bytes
        except Exception as exc:
            manifest['available'] = False
            manifest['groups'] = []
            manifest['cache_bytes'] = 0
            self._meshes = {}
            manifest['unavailable_reasons'].append(getattr(exc, 'code', 'display_preparation_failed'))
            manifest['error'] = str(exc)

    def manifest(self, model, revision, steps=()):
        self._prepare(model, revision)
        result = copy.deepcopy(self._manifest)
        source = model.display_provenance
        identity_owners = {identity: owner for owner, identity in source.step_ids.items()}
        entities = []
        for step in steps:
            identity = getattr(step, 'step_id', None)
            owner = identity_owners.get(identity, 0)
            count = result['entity_counts'].get(str(owner), 0) if owner else 0
            name = getattr(step, 'name', '')
            reason = ('initialization' if name == 'Structure Wafer' else
                      ('no_remaining_entity' if not count else None))
            if not result['available']:
                reason = result['unavailable_reasons'][-1]
            elif source.owners is None and reason != 'initialization':
                reason = 'unknown_provenance'
            entities.append({'step_id': identity, 'owner_id': owner or None,
                             'voxel_count': count, 'hideable': reason is None,
                             'unavailable_reason': reason})
        result['step_entities'] = entities
        return result

    def mesh(self, model, current_revision, owner_id, mat_id, *, revision=None):
        self._check_revision(current_revision, revision)
        self._prepare(model, current_revision)
        if not self._manifest['available']:
            code = self._manifest['unavailable_reasons'][-1]
            raise DisplayDataError(self._manifest['error'], code, 413 if code == 'display_budget_exceeded' else 503)
        try:
            return self._meshes[(owner_id, mat_id)]
        except KeyError:
            raise DisplayDataError('Unknown display group', 'unknown_display_group', 404) from None

    def slice(self, model, current_revision, axis, index, *, revision=None):
        self._check_revision(current_revision, revision)
        axis = str(axis).upper()
        if axis not in ('X', 'Y', 'Z'):
            raise DisplayDataError('Invalid display slice axis')
        dimension = 'XYZ'.index(axis)
        if index < 0 or index >= model.grid.shape[dimension]:
            raise DisplayDataError('Invalid display slice index')
        slice_cells = int(np.prod([n for i, n in enumerate(model.grid.shape) if i != dimension]))
        if slice_cells * 6 > self.max_slice_bytes:
            raise DisplayDataError('Structure display slice budget exceeded', 'display_budget_exceeded', 413)
        source = model.display_provenance.owners
        selection = [slice(None)] * 3
        selection[dimension] = index
        material = model.grid[tuple(selection)].T
        owner = np.zeros(material.shape, np.uint32) if source is None else source[tuple(selection)].T
        # Never expose stale owners in actual holes, and never mutate the source.
        owner = np.where(material != 0, owner, 0).astype('<u4')
        def encoded(array, dtype):
            return {'dtype': dtype, 'data_b64': base64.b64encode(array.tobytes(order='C')).decode('ascii')}
        return {'revision': int(current_revision), 'axis': axis, 'index': index,
                'index_max': model.grid.shape[dimension] - 1, 'shape': list(material.shape),
                'material': encoded(material.astype('<u2'), 'u16'), 'owner': encoded(owner, 'u32')}
