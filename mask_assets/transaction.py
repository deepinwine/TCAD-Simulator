"""Durable undo journal for the single session worker's mask/recipe commit."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.mask-transaction-', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


class MaskApplyTransaction:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).absolute()
        self.journal = self.root / '.mask-apply-journal'
        self.marker = self.root / '.mask-apply-pending.json'
        self.originals = {}

    def _target(self, relative: str) -> Path:
        value = Path(relative)
        if value.is_absolute() or '..' in value.parts or not value.parts:
            raise ValueError('Invalid mask transaction path')
        target = self.root / value
        if not target.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('Mask transaction path leaves session')
        if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent != self.root and parent.is_relative_to(self.root)):
            raise ValueError('Mask transaction symlinks are unsupported')
        return target

    def _check_journal(self) -> None:
        if self.journal.is_symlink() or self.marker.is_symlink():
            raise ValueError('Mask transaction journal symlinks are unsupported')

    @property
    def pending(self) -> bool:
        return self.marker.exists() or self.marker.is_symlink()

    def begin(self, paths=()) -> None:
        self.recover()
        self.journal.mkdir(exist_ok=True)
        self.originals = {}
        atomic_bytes(self.marker, b'{}')
        for path in paths:
            self.capture(path)

    def capture(self, path: Path) -> None:
        """Record the previous bytes before the caller can replace this file."""
        relative = Path(path).absolute().relative_to(self.root)
        path = self._target(str(relative))
        if str(relative) in self.originals:
            return
        exists = path.exists()
        if exists:
            atomic_bytes(self.journal / relative, path.read_bytes())
            directory = (self.journal / relative).parent
            while directory != self.root:
                fsync_directory(directory)
                directory = directory.parent
        self.originals[str(relative)] = exists
        atomic_bytes(self.marker, json.dumps(self.originals).encode('utf-8'))

    def recover(self) -> None:
        self._check_journal()
        if self.marker.exists():
            originals = json.loads(self.marker.read_text(encoding='utf-8'))
            if not isinstance(originals, dict) or any(type(value) is not bool for value in originals.values()):
                raise ValueError('Invalid mask transaction journal')
            # Validate all targets and backups before touching any state.
            for relative, existed in originals.items():
                self._target(relative)
                backup = self.journal / relative
                if existed and (not backup.resolve().is_relative_to(self.journal.resolve()) or backup.is_symlink()):
                    raise ValueError('Invalid mask transaction backup')
            for relative, existed in originals.items():
                path = self._target(relative)
                if existed:
                    atomic_bytes(path, (self.journal / relative).read_bytes())
                elif path.exists():
                    path.unlink()
                    fsync_directory(path.parent)
            self.marker.unlink()
            fsync_directory(self.root)
        if self.journal.exists():
            shutil.rmtree(self.journal)
            fsync_directory(self.root)

    def commit(self) -> None:
        # Persistence helpers may use buffered replace: flush files and their
        # directories before removing the durable undo marker.
        for relative in self.originals:
            path = self.root / relative
            if not path.exists():
                continue
            with path.open('rb') as handle:
                os.fsync(handle.fileno())
            directory = path.parent
            while directory != self.root:
                fsync_directory(directory)
                directory = directory.parent
        marker_bytes = self.marker.read_bytes()
        self.marker.unlink()
        try:
            fsync_directory(self.root)
        except Exception:
            atomic_bytes(self.marker, marker_bytes)
            raise
        # Journal garbage is harmless once the marker is durably absent.
        try:
            shutil.rmtree(self.journal)
        except OSError:
            pass
