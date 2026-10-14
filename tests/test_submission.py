"""A source handover must include runnable assets and exclude private runtime files."""

import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest


@pytest.fixture
def package(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'package_submission.py'
    spec = importlib.util.spec_from_file_location('package_submission', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'DESTINATION', tmp_path / 'GP')
    monkeypatch.setattr(module, 'ARCHIVE', tmp_path / 'GP.zip')
    return module


def put(root, name, content='fixture'):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_submission_excludes_runtime_secrets_and_generated_metadata(package):
    included = ['README.md', '.env.example', 'src/governance/static/index.html']
    excluded = [
        '.env.local',
        'docs/.env.private',
        'docs/private.key',
        'docs/state.db-wal',
        'docs/state.sqlite-shm',
        'docs/state.sqlite3-journal',
        'src/clarity_governance.egg-info/PKG-INFO',
        'src/governance/__pycache__/app.pyc',
        'data/governance.db',
        'unrelated-user-document.docx',
    ]
    for name in included + excluded:
        put(package.ROOT, name)
    package.copy_project()
    copied = {
        item.relative_to(package.DESTINATION).as_posix()
        for item in package.DESTINATION.rglob('*')
        if item.is_file()
    }
    assert copied == set(included)


def test_submission_archive_matches_manifest_and_replaces_stale_files(package):
    put(package.ROOT, 'README.md', 'handover')
    put(package.ROOT, 'src/governance/static/app.js', 'runnable asset')
    put(package.DESTINATION, 'old-version.txt')
    package.copy_project()
    assert package.write_manifest() == 2
    package.write_archive()
    manifest = json.loads((package.DESTINATION / 'submission-manifest.json').read_text())
    with ZipFile(package.ARCHIVE) as archive:
        assert set(archive.namelist()) == {
            'GP/README.md',
            'GP/src/governance/static/app.js',
            'GP/submission-manifest.json',
        }
        for entry in manifest['files']:
            assert (
                hashlib.sha256(archive.read('GP/' + entry['path'])).hexdigest() == entry['sha256']
            )


def test_submission_refuses_to_replace_an_outside_directory(package, tmp_path, monkeypatch):
    outside = tmp_path.parent / (tmp_path.name + '-outside')
    put(outside, 'keep.txt', 'preserve me')
    monkeypatch.setattr(package, 'DESTINATION', outside)
    with pytest.raises(RuntimeError, match='outside'):
        package.copy_project()
    assert (outside / 'keep.txt').read_text() == 'preserve me'
