"""The wildcard and query-error SI tables, built from the committed data files."""

import csv
import unittest

from census.tables import make_si_tables as si


class WildcardTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = si.wildcard()
        cls.rows = [r for r in cls.body.splitlines() if r.startswith("| ")][1:]

    def test_row_count(self):
        # 22 analysis packages plus the ImageJ/Fiji share row
        self.assertEqual(len(self.rows), 23)
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


@unittest.skipUnless(has_full_text_indicator(), 'Citation full_text indicator is omitted from the sanitised release')
class QueryErrorsTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = si.queryerrors()
        cls.rows = [r for r in cls.body.splitlines() if r.startswith("| ")][1:]

    def test_row_count(self):
        self.assertEqual(len(self.rows), 30)  # one per registry package


@unittest.skipUnless(has_full_text_indicator(), 'Citation full_text indicator is omitted from the sanitised release')
class NoToolWordTests(unittest.TestCase):
    def test_no_cell_says_tool(self):
        for body in (si.wildcard(), si.queryerrors()):
            self.assertNotIn("tool", body)
            self.assertNotIn("Tool", body)


if __name__ == "__main__":
    unittest.main()
