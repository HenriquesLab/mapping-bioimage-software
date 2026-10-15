"""Manifest checks tolerate local artefacts but still detect payload changes."""
import importlib.util
from pathlib import Path
import subprocess
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'release'))
spec = importlib.util.spec_from_file_location('release_check', Path(__file__).resolve().parents[1] / 'release/test_release.py')
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)


def test_payload_ignores_local_files_without_hiding_manifest_entries(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / '.gitignore').write_text('local-output/\ntracked.csv\n')
    for name in ('tracked.csv', 'unexpected.txt', 'MANIFEST.tsv', 'MANIFEST.sha256',
                 '__pycache__/probe.pyc', '.pytest_cache/state', 'local-output/plot.svg'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('local')
    assert release_check.archive_payload(tmp_path, {'.gitignore', 'tracked.csv'}) == {
        '.gitignore', 'tracked.csv', 'unexpected.txt'}


def test_payload_does_not_inherit_parent_repository_ignores(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / '.gitignore').write_text('release/build/\n')
    archive = tmp_path / 'release/build/archive'
    archive.mkdir(parents=True)
    (archive / 'README.md').write_text('published')
    (archive / 'unexpected.txt').write_text('unlisted')
    assert release_check.archive_payload(archive, {'README.md'}) == {
        'README.md', 'unexpected.txt'}
