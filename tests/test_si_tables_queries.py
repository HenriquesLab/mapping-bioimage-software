"""The wildcard and query-error SI tables, built from the committed data files."""

import csv
import unittest

import pandas as pd

from census.tables import make_si_tables as si


class WildcardTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = si.wildcard()
        cls.rows = [r for r in cls.body.splitlines() if r.startswith("| ")][1:]

    def test_row_count(self):
        tools = pd.read_csv(si.PROCESSED_DIR / "tools.csv")
        analysis = tools[tools.in_aggregate.astype(str).str.lower().eq("true")
                         & tools.category.ne("acquisition-suite")]
        self.assertEqual(len(self.rows), len(analysis) + 1)
        self.assertTrue(self.rows[-1].startswith("| ImageJ/Fiji share of analysis mentions "))

    def test_imagej_share_cell(self):
        cell = self.rows[-1].split(" | ")[1]
        self.assertRegex(cell, r"^\d+(\.\d)?% / \d+(\.\d)?% / \d+(\.\d)?%$")


def has_full_text_indicator():
    path = si.VALIDATION / 'citations_cited_not_named_2025.csv'
    if not path.is_file():
        return False
    with path.open(newline='') as stream:
        return 'full_text' in next(csv.reader(stream))


@unittest.skipUnless(has_full_text_indicator(), 'Citation validation CSV data/validation/citations_cited_not_named_2025.csv or its full_text flag is not shipped')  # noqa: E501
class QueryErrorsTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = si.queryerrors()
        cls.rows = [r for r in cls.body.splitlines() if r.startswith("| ")][1:]

    def test_row_count(self):
        self.assertEqual(len(self.rows), len(pd.read_csv(si.PROCESSED_DIR / "tools.csv")))

    def test_false_positive_rates_are_reported(self):
        self.assertIn('False-positive rate', self.body)
        for rate in ('2.5% (1/40)', '45.0% (18/40)', '0.0% (0/40)', '55% (22/40)', '100% (40/40)'):
            self.assertIn(rate, self.body)


@unittest.skipUnless(has_full_text_indicator(), 'Citation validation CSV data/validation/citations_cited_not_named_2025.csv or its full_text flag is not shipped')  # noqa: E501
class NoToolWordTests(unittest.TestCase):
    def test_no_cell_says_tool(self):
        for body in (si.wildcard(), si.queryerrors()):
            self.assertNotIn("tool", body)
            self.assertNotIn("Tool", body)


def test_registry_table_uses_current_aggregate_total():
    body = si.registry()
    rows = [line for line in body.splitlines() if line.startswith("| ")]
    assert len(rows) - 1 == 33
    assert "29-package total" in body
    assert "30-package total" not in body
    assert "28-package total" not in body
    assert "| Image-Pro | commercial package |" in body
    assert "| NIH Image | open platform |" in body
    assert "after about 2000" in body.lower()
    assert "| Adobe Photoshop | image-editing / figure-preparation software |" in body
    assert "| neither |" in next(line for line in rows if line.startswith("| NIH Image |"))
    assert "| neither |" in next(line for line in rows if line.startswith("| Adobe Photoshop |"))
    assert "| NIH Image |" not in si.literature()
    assert "| NIH Image |" not in si.methods_section()


def test_revision_precision_labels_use_historical_nih_sample(tmp_path, monkeypatch):
    import csv

    validation = tmp_path / 'validation'
    replicates = validation / 'replicates'
    replicates.mkdir(parents=True)
    for name in ('alias_precision_2025', 'alias_precision_core_2025'):
        for rep in (1, 2, 3):
            for annotator in ('deepseek', 'glm'):
                with (replicates / f'{name}_labels_{annotator}_r{rep}.csv').open('w', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['item_id', 'sense'])
                    writer.writerow([f'legacy|{rep}', 'software'])
    labels = validation / 'registry_precision_2026.csv'
    with labels.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['tool_id', 'year', 'pmcid', 'label', 'use', 'meaning'])
        for tool, n_false in (('imagepro', 3), ('nihimage', 28), ('photoshop', 0)):
            for i in range(40):
                year = '2024' if tool == 'nihimage' else '2025'
                label = 'false_positive' if i < n_false else 'software'
                use = 'image-processing-or-analysis' if tool == 'photoshop' else ''
                meaning = 'imagej-meant' if tool == 'nihimage' else ''
                writer.writerow([tool, year, f'PMC{tool}{i:02d}', label, use, meaning])
        for i in range(40):
            meaning = 'nih-image-program' if i < 32 else 'derivative' if i < 35 else 'unclear'
            label = 'false_positive' if i < 2 else 'software'
            writer.writerow(['nihimage', str(1995 + i % 9), f'PMCold{i:02d}', label, '', meaning])
    monkeypatch.setattr(si, 'VALIDATION', validation)
    precision = si._alias_precision()
    assert precision.get('imagepro') == (37, 40)
    assert precision.get('nihimage') == (38, 40)
    assert precision.get('photoshop') == (40, 40)


def test_published_registry_precision_labels_follow_the_scoped_criteria():
    labels = pd.read_csv(si.VALIDATION / 'registry_precision_2026.csv', dtype=str).fillna('')
    photoshop = labels[labels.tool_id == 'photoshop']
    assert len(photoshop) == 40
    assert set(photoshop.label) == {'software'}
    expected_use = {
        'figure-assembly': 11,
        'image-processing-or-analysis': 23,
        'illustration': 3,
        'listed-only': 2,
        'unclear': 1,
    }
    assert photoshop.use.value_counts().to_dict() == expected_use
    nih = labels[labels.tool_id == 'nihimage']
    recent = nih[nih.year.isin(['2024', '2025'])]
    historical = nih[nih.year.isin([str(y) for y in range(1995, 2004)])]
    allowed = {'nih-image-program', 'imagej-meant', 'derivative', 'unclear'}
    assert len(recent) == 40
    assert recent.meaning.value_counts().to_dict() == {
        'nih-image-program': 15, 'imagej-meant': 19, 'derivative': 3, 'unclear': 3,
    }
    assert recent.label.value_counts().to_dict() == {'false_positive': 28, 'software': 12}
    assert 1 <= len(historical) <= 40
    assert set(recent.meaning) <= allowed and set(historical.meaning) <= allowed
    assert historical.meaning.value_counts().to_dict() == {
        'nih-image-program': 22, 'derivative': 3, 'unclear': 15,
    }
    assert historical.label.value_counts().to_dict() == {'software': 22, 'false_positive': 18}
    assert len(nih) == 40 + len(historical)

if __name__ == "__main__":
    unittest.main()
