"""Keep article text out of the tracked public tree; report names, never values."""
import csv
import gzip
import json
from itertools import dropwhile
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROSE = ' '.join(['synthetic example words for checking the publication guard'] * 5)


TEXT_KEYS = {'title', 'abstract', 'full_text', 'sentence', 'sentences',
             'snippet', 'snippets', 'evidence', 'text', 'body'}


def allowed_field(relative, keys):
    name = relative.as_posix()
    # Release metadata describes our study, not source articles.
    if name in {'.zenodo.json', 'CITATION.cff'}:
        return True
    # Configuration contains our matching rules and regular expressions.
    if relative.parent == Path('config') and relative.suffix in {'.json', '.yml'}:
        return True
    # Design notes explain our sampling and deviations.
    if keys[-1] == 'note' and (relative.name.endswith('_design.json') or
            name in {'data/processed/replicates/abstract_designs.json',
                     'data/processed/replicates/deviation_summary.csv'}):
        return True
    # Alias queries are our search expressions.
    if relative.name.startswith('alias_precision_') and (
            keys[:1] == ('queries',) or keys[:2] == ('inputs', 'queries')):
        return True
    # Venue values are journal names.
    if keys[-1] == 'venue':
        return True
    # These two columns contain checked annotator paraphrases, not quotations.
    return (name == 'data/validation/replicates/cellpose_workflow_2025_human_r1.csv'
            and keys[-1] in {'methods_or_fulltext_details', 'external_context_details'})


def scan_file(path, relative):
    findings = []

    def check(keys, values):
        if allowed_field(relative, keys):
            return
        key = keys[-1].strip().lower()
        flag_only = all(isinstance(value, (str, bool)) and
                        str(value).strip().lower() in {'true', 'false', ''}
                        for value in values)
        if key in TEXT_KEYS and not (key == 'full_text' and flag_only):
            reason = 'text key'
        elif any(isinstance(value, str) and len(value) >= 150 and
                 len(re.findall(r'\b[a-z]+\b', value)) >= 20 for value in values):
            reason = 'long prose'
        else:
            return
        findings.append(f'{relative.as_posix()}: {".".join(keys)} ({reason})')

    def walk(value, keys=()):
        if isinstance(value, dict):
            for key, child in value.items():
                check(keys + (key,), [child])
                walk(child, keys + (key,))
        elif isinstance(value, list):
            for child in value:
                if keys and not isinstance(child, (dict, list)):
                    check(keys, [child])
                walk(child, keys)
        elif not keys and isinstance(value, str):
            check(('<root>',), [value])

    if path.suffix == '.json':
        walk(json.loads(path.read_text(encoding='utf-8')))
    else:
        opener = gzip.open if path.name.endswith('.gz') else open
        with opener(path, 'rt', encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(dropwhile(lambda line: line.lstrip().startswith('#'), stream))
            headers = next(reader, [])
            columns = [[] for _ in headers]
            for row in reader:
                for index, value in enumerate(row):
                    if index < len(columns):
                        columns[index].append(value)
                    else:
                        check(('<extra column>',), [value])
            for header, values in zip(headers, columns):
                check((header,), values)
    return sorted(set(findings))


@pytest.mark.parametrize('prefix', ['', '# synthetic provenance\n# second comment\n'])
def test_scanner_rejects_article_title(tmp_path, prefix):
    path = tmp_path / 'probe.csv'
    path.write_text(prefix + 'title\n' + PROSE + '\n')
    assert scan_file(path, Path('probe.csv')) == ['probe.csv: title (text key)']


@pytest.mark.parametrize('suffix', ['.csv', '.csv.gz', '.json'])
def test_scanner_rejects_unlabelled_prose(tmp_path, suffix):
    path = tmp_path / ('probe' + suffix)
    if suffix == '.json':
        path.write_text(json.dumps({'nested': [{'details': PROSE}]}))
        field = 'nested.details'
    else:
        opener = gzip.open if suffix.endswith('.gz') else open
        with opener(path, 'wt', newline='') as stream:
            csv.writer(stream).writerows([['details'], [PROSE]])
        field = 'details'
    assert scan_file(path, Path(path.name)) == [f'{path.name}: {field} (long prose)']


@pytest.mark.parametrize('value,allowed', [('True', True), ('False', True), ('', True), ('article words', False)])
def test_full_text_must_be_a_flag(tmp_path, value, allowed):
    path = tmp_path / 'probe.csv'
    with path.open('w', newline='') as stream:
        csv.writer(stream).writerows([['full_text'], [value]])
    assert bool(scan_file(path, Path(path.name))) is not allowed


@pytest.mark.parametrize('key', sorted(TEXT_KEYS - {'full_text'}))
def test_scanner_rejects_nested_text_keys_even_when_empty(tmp_path, key):
    path = tmp_path / 'probe.json'
    path.write_text(json.dumps({'records': [{key: ''}]}))
    assert scan_file(path, Path(path.name)) == [f'probe.json: records.{key} (text key)']


@pytest.mark.parametrize('relative,field', [
    ('.zenodo.json', 'description'),
    ('config/keywords.json', 'rules'),
    ('data/validation/replicates/example_design.json', 'note'),
    ('data/processed/replicates/abstract_designs.json', 'note'),
    ('data/processed/replicates/deviation_summary.csv', 'note'),
    ('data/validation/frames/alias_precision_2025_frame.json', 'queries'),
    ('data/validation/alias_precision_2025_items.json', 'inputs.queries'),
    ('data/example.csv', 'venue'),
    ('data/validation/replicates/cellpose_workflow_2025_human_r1.csv', 'methods_or_fulltext_details'),
    ('data/validation/replicates/cellpose_workflow_2025_human_r1.csv', 'external_context_details'),
])
def test_scanner_allows_documented_own_text(tmp_path, relative, field):
    path = tmp_path / Path(relative).name
    if path.suffix == '.json':
        value = PROSE
        for key in reversed(field.split('.')):
            value = {key: value}
        path.write_text(json.dumps(value))
    else:
        with path.open('w', newline='') as stream:
            csv.writer(stream).writerows([[field], [PROSE]])
    assert scan_file(path, Path(relative)) == []


def test_note_exception_does_not_cover_arbitrary_files(tmp_path):
    path = tmp_path / 'probe.json'
    path.write_text(json.dumps({'note': PROSE}))
    assert scan_file(path, Path(path.name)) == ['probe.json: note (long prose)']


def test_article_text_guard_checks_untracked_notebook_data(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), 'ROOT', tmp_path)
    monkeypatch.setattr(subprocess, 'check_output', lambda *args, **kwargs: b'')
    data = tmp_path / 'notebooks/data'
    data.mkdir(parents=True)
    path = data / 'probe.csv'
    path.write_text('count\n12\n')
    test_tracked_data_contains_no_article_text()
    path.write_text('title\n' + PROSE + '\n')
    with pytest.raises(AssertionError, match='notebooks/data/probe.csv: title'):
        test_tracked_data_contains_no_article_text()


def test_tracked_data_contains_no_article_text():
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    # Include new notebook inputs before staging them for the public release.
    notebook_data = [p.relative_to(ROOT).as_posix()
                     for p in (ROOT / 'notebooks/data').rglob('*') if p.is_file()]
    findings = []
    for name in sorted(set(tracked + notebook_data)):
        if name.endswith(('.csv', '.csv.gz', '.json')):
            findings.extend(scan_file(ROOT / name, Path(name)))
    assert not findings, '\n'.join(findings)
