"""Offline checks for query scope, fair exclusions and reach denominators."""
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from census._registry import Registry, Tool, build_boolean_query, load_registry


class BlotTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('census.build.build_blot_sensitivity'),
                             'blot sensitivity builder is missing')
        from census.build import build_blot_sensitivity
        self.b = build_blot_sensitivity
        self.reg = Registry(2010, 2025, '(microscopy OR microscope) AND HAS_FT:Y', [
            Tool('imagej', 'ImageJ / Fiji', 'general-platform', False, ['ImageJ', 'Fiji']),
            Tool('other', 'Other', 'library', False, ['Other']),
            Tool('suite', 'Suite', 'acquisition-suite', False, ['Suite']),
            Tool('matlab', 'MATLAB', 'commercial', False, ['MATLAB'], in_aggregate=False)])

    def test_queries_cover_every_tool_year_and_methods_all_clauses(self):
        reg = load_registry()
        jobs = self.b.build_queries(reg)
        self.assertEqual(len(jobs), 17 * (len(reg.tools) + 1) * 2)
        for year in range(2010, 2026):
            for tool in reg.tools:
                base = jobs[('full_text', year, tool.id, 'all')]
                self.assertEqual(base, build_boolean_query(tool, reg.context_query) + f' AND PUB_YEAR:{year}')
                blot = jobs[('full_text', year, tool.id, 'with_blot')]
                self.assertTrue(blot.startswith(base + ' AND ('))
                for term in ('western blot', 'immunoblot', 'blotting', 'densitometry',
                             'densitometric', 'gel quantification'):
                    self.assertIn(f'"{term}"', blot)
        self.assertNotIn(('methods', 2020, 'imagej', 'all'), jobs)
        query = jobs[('methods', 2025, 'imagej', 'with_blot')]
        for term in reg.by_id('imagej').terms('METHODS:'):
            self.assertIn(term, query)
        self.assertIn('(METHODS:"microscopy" OR METHODS:"microscope") AND HAS_FT:Y', query)
        for term in ('western blot', 'immunoblot', 'blotting', 'densitometry',
                     'densitometric', 'gel quantification'):
            self.assertIn(f'METHODS:"{term}"', query)

    def counts(self):
        values = {'corpus': (1000, 200), 'imagej': (100, 60),
                  'other': (50, 10), 'suite': (500, 1), 'matlab': (300, 1)}
        return {key: values[key[2]][key[3] == 'with_blot']
                for key in self.b.build_queries(self.reg)}

    def test_fair_share_and_both_reach_denominators(self):
        frame = self.b.summarize(self.reg, self.counts())
        self.assertEqual(len(frame), 17 * 4)
        ij = frame[(frame.scope == 'full_text') & (frame.year == 2025) & (frame.tool_id == 'imagej')].iloc[0]
        self.assertEqual((ij.papers_all, ij.papers_with_blot, ij.papers_without_blot), (100, 60, 40))
        self.assertEqual(ij.imagej_reach_all_pct, 10)
        self.assertEqual(ij.imagej_reach_without_blot_pct, 4)
        self.assertEqual(ij.imagej_reach_in_blot_free_corpus_pct, 5)
        self.assertEqual(ij.analysis_mentions_all, 150)
        self.assertEqual(ij.analysis_mentions_without_blot, 80)
        self.assertAlmostEqual(ij.imagej_share_analysis_all_pct, 100 * 100 / 150)
        self.assertEqual(ij.imagej_share_analysis_without_blot_pct, 50)
        self.assertEqual(ij.imagej_blot_pct, 60)
        zero = {key: 0 for key in self.counts()}
        self.assertTrue(math.isnan(self.b.summarize(self.reg, zero).iloc[0].imagej_reach_all_pct))
        bad = self.counts()
        bad[('full_text', 2010, 'imagej', 'with_blot')] = 101
        with self.assertRaises(ValueError):
            self.b.summarize(self.reg, bad)

    def test_main_writes_complete_csv_offline(self):
        jobs = self.b.build_queries(self.reg)
        response = dict(zip(jobs.values(), self.counts().values()))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(self.b, 'load_registry', return_value=self.reg), \
                 patch.object(self.b, '_hit_count', side_effect=response.__getitem__), \
                 patch.object(self.b, 'PROCESSED_DIR', Path(tmp)):
                self.b.main()
            frame = pd.read_csv(Path(tmp) / 'blot_sensitivity_yearly.csv')
            self.assertEqual(len(frame), 68)
            self.assertEqual(set(frame[frame.scope == 'full_text'].year), set(range(2010, 2026)))
            self.assertEqual(set(frame[frame.scope == 'methods'].year), {2025})
            self.assertEqual(set(frame.tool_id), {'imagej', 'other', 'suite', 'matlab'})


if __name__ == '__main__':
    unittest.main()
