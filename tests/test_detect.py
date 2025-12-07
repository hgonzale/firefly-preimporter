from pathlib import Path

import pytest

from firefly_preimporter.detect import detect_format, gather_jobs, iter_jobs
from firefly_preimporter.models import SourceFormat


def test_detect_format_extensions(tmp_path: Path) -> None:
    csv_file = tmp_path / 'statement.csv'
    csv_file.write_text('header\n', encoding='utf-8')
    ofx_file = tmp_path / 'statement.ofx'
    ofx_file.write_text('ofx', encoding='utf-8')

    assert detect_format(csv_file) is SourceFormat.CSV
    assert detect_format(ofx_file) is SourceFormat.OFX


def test_iter_jobs_directory(tmp_path: Path) -> None:
    csv_file = tmp_path / 'a.csv'
    csv_file.write_text('header\n', encoding='utf-8')
    ofx_file = tmp_path / 'b.ofx'
    ofx_file.write_text('data', encoding='utf-8')
    ignored = tmp_path / 'notes.txt'
    ignored.write_text('ignore', encoding='utf-8')

    jobs = list(iter_jobs(tmp_path))
    assert len(jobs) == 2
    assert jobs[0].source_path == csv_file
    assert jobs[0].source_format is SourceFormat.CSV
    assert jobs[1].source_format is SourceFormat.OFX


def test_iter_jobs_file_unknown_extension(tmp_path: Path) -> None:
    weird = tmp_path / 'weird.ext'
    weird.write_text('x', encoding='utf-8')

    with pytest.raises(ValueError, match='Unsupported input format'):
        list(iter_jobs(weird))


def test_iter_jobs_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / 'unknown'
    with pytest.raises(FileNotFoundError):
        list(iter_jobs(missing))


def test_gather_jobs_multiple_targets(tmp_path: Path) -> None:
    csv_file = tmp_path / 'first.csv'
    csv_file.write_text('header\n', encoding='utf-8')
    folder = tmp_path / 'nested'
    folder.mkdir()
    other = folder / 'second.csv'
    other.write_text('header\n', encoding='utf-8')

    jobs = gather_jobs([csv_file, folder])
    assert {job.source_path for job in jobs} == {csv_file, other}
