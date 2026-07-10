"""Input discovery helpers for Firefly Preimporter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from firefly_preimporter.models import ProcessingJob, SourceFormat
from ofxtools.header import OFXHeaderError, parse_header

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from collections.abc import Iterable, Iterator
    from pathlib import Path

LOGGER = logging.getLogger(__name__)

FORMAT_MAP: dict[str, SourceFormat] = {
    '.csv': SourceFormat.CSV,
    '.ofx': SourceFormat.OFX,
    '.qfx': SourceFormat.OFX,
    '.qbo': SourceFormat.OFX,
}
"""Mapping between file suffixes and supported ``SourceFormat`` values."""


def _is_generated_output(path: Path) -> bool:
    """Return True if ``path`` looks like a Preimporter-generated CSV."""

    return path.suffix.lower() == '.csv' and path.name.endswith('.firefly.csv')


def _looks_like_ofx(path: Path) -> bool:
    """Return True if ``path``'s content parses as a valid OFX/QBO header.

    Only the header block is read, not the full body, so this is cheap even
    for large files. ``parse_header`` loops forever on an empty stream, so
    empty files are rejected up front rather than passed to it.
    """

    if path.stat().st_size == 0:
        return False
    try:
        with path.open('rb') as handle:
            parse_header(handle)
    except (OFXHeaderError, UnicodeDecodeError, ValueError, OSError):
        return False
    return True


def detect_format(path: Path) -> SourceFormat:
    """Infer the ``SourceFormat`` for ``path``.

    Suffixes in ``FORMAT_MAP`` are resolved directly. An unrecognized suffix
    falls back to sniffing the file content for a valid OFX header, since
    some banks export OFX-compatible data (e.g. QBO) under unexpected
    extensions.
    """

    fmt = FORMAT_MAP.get(path.suffix.lower())
    if fmt is not None:
        return fmt
    if _looks_like_ofx(path):
        LOGGER.info('Detected OFX content in %s despite unrecognized suffix %r', path.name, path.suffix)
        return SourceFormat.OFX
    return SourceFormat.UNKNOWN


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
        if _is_generated_output(entry):
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
