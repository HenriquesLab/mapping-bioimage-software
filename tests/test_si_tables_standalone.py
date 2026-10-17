from unittest.mock import patch

import census.tables.make_si_tables as si


def test_main_writes_local_tables_without_manuscript(tmp_path):
    out = tmp_path / 'supplementary_tables.md'
    tables = {'one': lambda: '| a |', 'broken': lambda: {}['missing']}
    with patch.object(si, 'SI', tmp_path / 'missing.md'), patch.object(si, 'OUTPUT', out), \
            patch.object(si, 'TABLES', tables):
        si.main()
    assert out.read_text() == '## one\n\n| a |\n'
