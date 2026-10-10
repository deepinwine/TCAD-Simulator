"""Display-only voxel ownership captured during normal Structure construction.

Zero means unknown (including legacy grids). The canonical material grid remains
independent. Owners allocate lazily: uint32 costs 8 MiB for a 128 cubed domain.
"""
import uuid

import numpy as np


def normalize_step_id(value=None):
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else str(uuid.uuid4())
    except (ValueError, AttributeError):
        return str(uuid.uuid4())


def normalize_step_identities(steps, *, preserve_ids=False):
    """Keep the first valid identity; regenerate invalid or colliding later IDs."""
    seen = set()
    prepared = []
    for step in steps:
        identity = normalize_step_id(getattr(step, 'step_id', None))
        if identity in seen:
            identity = normalize_step_id()
        if preserve_ids and identity != getattr(step, 'step_id', None):
            raise ValueError('Invalid source-bound step identity collision')
        prepared.append((step, identity))
        seen.add(identity)
    for step, identity in prepared:
        step.step_id = identity


def validate_source_bound_identities(blobs, state):
    """Reject identity repairs before a source-bearing snapshot mutates a session."""
    if not isinstance(state, dict) or state.get('display_owners') is None:
        return
    seen = set()
    for blob in blobs or []:
        identity = blob.get('step_id') if isinstance(blob, dict) else None
        if normalize_step_id(identity) != identity or identity in seen:
            raise ValueError('Invalid source-bound step identity collision')
        seen.add(identity)
    step_ids = state.get('display_step_ids', {})
    if not isinstance(step_ids, dict) or any(identity not in seen for identity in step_ids.values()):
        raise ValueError('Invalid source-bound display step identity mapping')


class DisplayProvenance:
    def __init__(self, *, max_bytes=256 * 1024 * 1024, max_steps=65536):
        self.max_bytes = max_bytes
        self.max_steps = max_steps
        self.owners = None
        self.step_ids = {}

    def invalidate(self):
        self.owners = None
        self.step_ids = {}

    def owner_for(self, step_id):
        for owner, identity in self.step_ids.items():
            if identity == step_id:
                return owner
        return 0

    def prepare(self, shape, step_id, additions):
        """Validate and allocate before any canonical geometry write."""
        if self.owners is not None and (self.owners.shape != shape or not self.owners.flags.writeable):
            raise ValueError('Structure display provenance requires writable matching owners')
        if additions is None or not additions.any():
            return
        required = int(np.prod(shape, dtype=object)) * np.dtype(np.uint32).itemsize
        if required > self.max_bytes:
            raise ValueError('Structure display provenance exceeds owner memory budget')
        if not self.owner_for(step_id) and (
            len(self.step_ids) >= self.max_steps or max(self.step_ids, default=0) >= np.iinfo(np.uint32).max
        ):
            raise ValueError('Structure display provenance exceeds step identity budget')
        if self.owners is None:
            self.owners = np.zeros(shape, dtype=np.uint32)

    def record(self, grid, step_id, additions):
        if self.owners is None:
            return
        self.owners[grid == 0] = 0
        if additions is not None and additions.any():
            owner = self.owner_for(step_id)
            if not owner:
                owner = max(self.step_ids, default=0) + 1
                self.step_ids[owner] = step_id
            self.owners[additions & (grid != 0)] = owner

    def restore(self, owners, step_ids, grid):
        if owners is None:
            self.invalidate()
            return
        if not isinstance(owners, np.ndarray) or owners.shape != grid.shape or owners.dtype != np.uint32:
            raise ValueError('Invalid Structure display owner snapshot')
        if owners.nbytes > self.max_bytes or not isinstance(step_ids, dict) or len(step_ids) > self.max_steps:
            raise ValueError('Invalid Structure display provenance snapshot budget')
        identities = {}
        for key, value in step_ids.items():
            owner = int(key)
            if owner <= 0 or owner > np.iinfo(np.uint32).max or not isinstance(value, str):
                raise ValueError('Invalid Structure display step identity snapshot')
            try:
                if str(uuid.UUID(value)) != value or value in identities.values():
                    raise ValueError()
            except ValueError:
                raise ValueError('Invalid Structure display step identity snapshot') from None
            identities[owner] = value
        if any(int(owner) not in identities for owner in np.unique(owners) if owner):
            raise ValueError('Unknown Structure display owner in snapshot')
        owners[grid == 0] = 0
        self.owners = owners
        self.step_ids = identities
