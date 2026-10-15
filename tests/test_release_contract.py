"""Release exact committed bytes and refuse dirty or unsafe sources."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

SPEC = importlib.util.spec_from_file_location('builder_contract', Path(__file__).resolve().parents[1] / 'release/make_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    (root / '.gitignore').write_text('release/build/\n')
    (root / 'tests').mkdir()
    (root / 'tests/test_no_article_text.py').write_text('def test_safe():\n    assert True\n')
    (root / 'data').mkdir()
    (root / 'data/values.csv').write_bytes(b'id,note\n1,our design\n')
    (root / 'extra.txt').write_text('tracked extra file\n')
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    commit(root)
    monkeypatch.setattr(release, 'ROOT', root)
    return root


def commit(root):
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Release Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture'], check=True)


def test_release_copies_every_tracked_byte(repo, monkeypatch):
    dest, _ = release.build('test')
    tracked = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z']).decode().strip('\0').split('\0')
    for name in tracked:
        assert (dest / name).read_bytes() == (repo / name).read_bytes()
    assert {p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()} == set(tracked) | {'MANIFEST.tsv', 'MANIFEST.sha256', 'PROVENANCE.json', 'ENVIRONMENT.txt', 'GIT_COMMIT.txt'}
    monkeypatch.setitem(sys.modules, 'make_release', release)
    spec = importlib.util.spec_from_file_location('contract_checker', Path(SPEC.origin).with_name('test_release.py'))
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    checker.archive_checks(dest)
    (dest / 'extra.txt').write_text('tampered')
    with pytest.raises(AssertionError):
        checker.archive_checks(dest)


@pytest.mark.parametrize('change', ['tracked', 'staged', 'untracked'])
def test_release_refuses_dirty_tree(repo, change):
    path = repo / ('extra.txt' if change != 'untracked' else 'new.txt')
    path.write_text('changed\n')
    if change == 'staged':
        subprocess.run(['git', '-C', str(repo), 'add', 'extra.txt'], check=True)
    with pytest.raises(RuntimeError, match='dirty'):
        release.build('test')
    assert not (repo / 'release/build/mapping-bioimage-software-test').exists()


def test_release_refuses_failed_article_guard(repo):
    (repo / 'tests/test_no_article_text.py').write_text('def test_safe():\n    assert False\n')
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
    commit(repo)
    with pytest.raises(RuntimeError, match='article-text'):
        release.build('test')
    assert not (repo / 'release/build/mapping-bioimage-software-test').exists()
