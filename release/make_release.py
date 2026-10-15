#!/usr/bin/env python3
"""Build an offline Zenodo directory from the clean committed tree plus provenance."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
PROVENANCE = {'MANIFEST.tsv', 'MANIFEST.sha256', 'PROVENANCE.json',
              'ENVIRONMENT.txt', 'GIT_COMMIT.txt'}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def environment(code_paths: list[Path]) -> str:
    imports = set()
    for path in code_paths:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(n.name.split('.')[0] for n in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imports.add(node.module.split('.')[0])
    imports.difference_update(sys.stdlib_module_names)
    mapping = importlib.metadata.packages_distributions()
    distributions = {d.lower().replace('_', '-') for m in imports for d in mapping.get(m, [])}
    # pip freeze is run through the current interpreter. Include only
    # directly imported distributions, not their transitive dependencies.
    result = subprocess.run([str(PYTHON), '-m', 'pip', 'freeze'], capture_output=True,
                            text=True, check=True, timeout=60)
    selected = []
    for line in result.stdout.splitlines():
        name = re.split(r'==| @ ', line, maxsplit=1)[0].lower().replace('_', '-')
        if name in distributions:
            selected.append(line)
    version = subprocess.check_output([str(PYTHON), '--version'], text=True).strip()
    return (f'Interpreter: {PYTHON.name}\n{version}\n'
            'Scope: directly imported installed packages in archived pipeline code; '
            'standard-library and transitive-only packages omitted.\n'
            f'Imported modules: {", ".join(sorted(imports))}\n\n'
            + '\n'.join(sorted(selected)) + '\n')


def git(*args: str) -> str:
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True)


def build(version: str, output: Path | None = None) -> tuple[Path, dict]:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', version):
        raise ValueError('version must be a safe folder-name component')
    dest = output or ROOT / 'release/build' / f'mapping-bioimage-software-{version}'
    if dest.exists():
        raise FileExistsError(f'refusing to overwrite {dest}')
    if git('status', '--porcelain', '--untracked-files=all'):
        raise RuntimeError('refusing to build from a dirty working tree')
    commit = git('rev-parse', 'HEAD').strip()
    tracked = set(git('ls-files', '-z').rstrip('\0').split('\0'))
    if tracked & PROVENANCE:
        raise RuntimeError('tracked files collide with release provenance names')
    # Capture output so a failed guard cannot print any article contents.
    guard = subprocess.run([str(PYTHON), '-B', '-m', 'pytest', '-q',
                            '-p', 'no:cacheprovider', 'tests/test_no_article_text.py'], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
    if guard.returncode:
        raise RuntimeError('article-text guard failed; archive not created')
    if git('status', '--porcelain', '--untracked-files=all') or git('rev-parse', 'HEAD').strip() != commit:
        raise RuntimeError('source became dirty or HEAD changed during article-text check')
    with tempfile.TemporaryFile() as stream:
        subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', commit],
                       stdout=stream, check=True, timeout=60)
        stream.seek(0)
        with tarfile.open(fileobj=stream) as archive:
            members = archive.getmembers()
            exported = {m.name for m in members if not m.isdir()}
            if exported != tracked:
                raise RuntimeError('git archive differs from tracked files (check export-ignore attributes)')
            dest.mkdir(parents=True)
            archive.extractall(dest, filter='data')
    report = dict(version=version, offline=True, git_commit=commit,
                  git_status='', tracked_files=sorted(tracked),
                  snapshot_note='Exact committed tree plus five provenance files; no data transformations.')
    (dest / 'GIT_COMMIT.txt').write_text(commit + '\n', encoding='utf-8')
    (dest / 'ENVIRONMENT.txt').write_text(environment(sorted((dest / 'census').rglob('*.py'))), encoding='utf-8')
    (dest / 'PROVENANCE.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    paths = sorted(p for p in dest.rglob('*') if p.is_file())
    with (dest / 'MANIFEST.tsv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
        writer.writerow(['path', 'bytes', 'sha256'])
        for path in paths:
            writer.writerow([path.relative_to(dest).as_posix(), path.stat().st_size, digest(path)])
    (dest / 'MANIFEST.sha256').write_text(digest(dest / 'MANIFEST.tsv') + '  MANIFEST.tsv\n', encoding='utf-8')
    files = [p for p in dest.rglob('*') if p.is_file()]
    return dest, dict(folder=str(dest), files=len(files),
                      bytes=sum(p.stat().st_size for p in files), git_commit=commit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=VERSION)
    parser.add_argument('--output', type=Path, help='new archive directory; existing directories are refused')
    args = parser.parse_args()
    _, summary = build(args.version, args.output)
    # Keep terminal output bounded even when many cache pages are missing.
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:18000])


if __name__ == '__main__':
    main()
