#!/usr/bin/env python3
"""Offline checks for metadata and exact tracked-tree archive integrity."""
import argparse
import csv
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

import make_release as release


def checks():
    # An installed backport must not turn a standard-library import into a dependency.
    from unittest.mock import patch
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory(dir=release.ROOT / 'release') as tmp:
        code = Path(tmp) / 'probe.py'
        code.write_text('import pathlib\nimport pandas\n')
        with patch.object(release.importlib.metadata, 'packages_distributions', return_value={'pathlib': ['pathlib'], 'pandas': ['pandas']}), patch.object(release.subprocess, 'run', return_value=SimpleNamespace(stdout='pathlib==1.0.1\npandas==2.3.0\n')), patch.object(release.subprocess, 'check_output', return_value='Python 3.11\n'):
            env = release.environment([code])
            assert 'pandas==2.3.0' in env and 'pathlib==1.0.1' not in env
            assert '/' + 'Users/' not in env
    cff = release.ROOT / 'CITATION.cff'
    validator = shutil.which('cffconvert')
    if validator:
        subprocess.run([validator, '--infile', str(cff), '--validate'], check=True, capture_output=True, text=True)
    else:
        data = yaml.safe_load(cff.read_text())
        assert {'cff-version', 'message', 'title', 'authors', 'type', 'license', 'version'} <= data.keys()
        assert data['cff-version'] == '1.2.0' and data['type'] == 'software'
        assert data['license'] == ['MIT', 'CC-BY-4.0'] and data['version'] == '2026.10.20'
        assert len(data['authors']) == 6
    citation = yaml.safe_load(cff.read_text())
    zenodo = json.loads((release.ROOT / '.zenodo.json').read_text())
    doi = '10.5281/zenodo.23395935'
    assert citation['doi'] == zenodo['doi'] == doi
    assert {'type': 'doi', 'value': doi} in citation['identifiers']
    assert citation['date-released'] == '2026-10-20'
    assert citation['version'] == zenodo['version'] == '2026.10.20'
    manuscript = release.ROOT.parent / 'MANUSCRIPT/00_CONFIG.yml'
    if manuscript.exists():
        config = yaml.safe_load(manuscript.read_text())
        citation = yaml.safe_load(cff.read_text())
        zenodo = json.loads((release.ROOT / '.zenodo.json').read_text())
        assert citation['keywords'] == zenodo['keywords'] == config['keywords']
        assert zenodo['upload_type'] == 'software' and zenodo['license'] == 'cc-by-4.0'
        assert len(zenodo['creators']) == len(config['authors']) == 6
        for author, c, z in zip(config['authors'], citation['authors'], zenodo['creators']):
            assert c['orcid'] == 'https://orcid.org/' + author['orcid'] and z['orcid'] == author['orcid']
            assert c['affiliation'] == z['affiliation'] == '; '.join(author['affiliations'])
    print('PASS: environment and metadata' + (' (cffconvert)' if validator else ' (required-key fallback)'))


def archive_payload(root, manifest_paths):
    # Always validate manifest entries, even if a local ignore rule matches them.
    files = {p.relative_to(root).as_posix() for p in root.rglob('*')
             if p.is_file() and not {'.git', '__pycache__', '.pytest_cache',
                                     '.ipynb_checkpoints'}.intersection(p.relative_to(root).parts)}
    extras = files - manifest_paths - {'MANIFEST.tsv', 'MANIFEST.sha256'}
    if extras and (root / '.git').exists():
        ignored = subprocess.run(
            ['git', '-C', str(root), 'check-ignore', '--no-index', '-z', '--stdin'],
            input='\0'.join(sorted(extras)) + '\0', capture_output=True, text=True,
            timeout=30)
        if ignored.returncode not in (0, 1):
            raise RuntimeError(ignored.stderr)
        files.difference_update(ignored.stdout.rstrip('\0').split('\0'))
    return files - {'MANIFEST.tsv', 'MANIFEST.sha256'}



def archive_checks(root):
    with (root / 'MANIFEST.tsv').open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    names = {r['path'] for r in rows}
    assert len(names) == len(rows), 'duplicate manifest paths'
    assert archive_payload(root, names) == names
    report = json.loads((root / 'PROVENANCE.json').read_text())
    commit = (root / 'GIT_COMMIT.txt').read_text().strip()
    assert commit == report['git_commit']
    tracked = set(release.git('ls-tree', '-r', '--name-only', '-z', commit).rstrip('\0').split('\0'))
    assert set(report['tracked_files']) == tracked
    assert names | {'MANIFEST.tsv', 'MANIFEST.sha256'} == tracked | release.PROVENANCE
    for row in rows:
        path = root / row['path']
        assert path.stat().st_size == int(row['bytes']) and release.digest(path) == row['sha256'], row['path']
    assert (root / 'MANIFEST.sha256').read_text() == release.digest(root / 'MANIFEST.tsv') + '  MANIFEST.tsv\n'
    # Compare every tracked byte directly with the recorded commit, independently of the manifest.
    for name in tracked:
        original = subprocess.check_output(['git', '-C', str(release.ROOT), 'show', f'{commit}:{name}'])
        assert (root / name).read_bytes() == original, name
    print(f'PASS: {len(rows)} payload checksums, {len(names) + 2} files; exact tracked tree plus provenance')


def test_environment_metadata():
    checks()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    checks()
    if args.archive:
        archive_checks(args.archive)
