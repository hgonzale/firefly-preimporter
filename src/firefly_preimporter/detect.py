"""Input discovery helpers for Firefly Preimporter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from firefly_preimporter.models import ProcessingJob, SourceFormat

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from collections.abc import Iterable, Iterator
    from pathlib import Path

FORMAT_MAP: dict[str, SourceFormat] = {
    '.csv': SourceFormat.CSV,
    '.ofx': SourceFormat.OFX,
    '.qfx': SourceFormat.OFX,
}
"""Mapping between file suffixes and supported ``SourceFormat`` values."""


def detect_format(path: Path) -> SourceFormat:
    """Infer the ``SourceFormat`` for ``path`` based on its suffix."""

    return FORMAT_MAP.get(path.suffix.lower(), SourceFormat.UNKNOWN)


def iter_jobs(target: Path) -> Iterator[ProcessingJob]:
    """Yield ``ProcessingJob`` entries for ``target`` (file or directory)."""

    expanded = target.expanduser()
    if expanded.is_file():
        fmt = detect_format(expanded)
        if fmt is SourceFormat.UNKNOWN:
            raise ValueError(f'Unsupported input format: {expanded.suffix}')
        yield ProcessingJob(source_path=expanded, source_format=fmt)
        return

    if not expanded.is_dir():
        raise FileNotFoundError(f'Input path not found: {expanded}')

    for entry in sorted(expanded.iterdir()):
        if not entry.is_file():
            continue
        fmt = detect_format(entry)
        if fmt is SourceFormat.UNKNOWN:
            continue
        yield ProcessingJob(source_path=entry, source_format=fmt)


def gather_jobs(paths: Iterable[Path]) -> list[ProcessingJob]:
    """Collect processing jobs for all provided ``paths``."""

    jobs: list[ProcessingJob] = []
    for path in paths:
        jobs.extend(iter_jobs(path))
    return jobs
