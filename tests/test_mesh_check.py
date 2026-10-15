"""Tests for the MeSH check: mapping, seeded sample and offline statistics.

Steps that need the local text corpus or the Europe PMC response cache skip
with a reason, so the public archive still runs everything else.
"""
from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import census.validation.mesh_check as mc
from census.figures.domains import DOMAINS

AREA_CSV = mc.PROCESSED_DIR / mc.AREA_CSV_NAME
PAPER_CSV = mc.PROCESSED_DIR / mc.PAPER_CSV_NAME
CONSUMED = {'area', 'shown_in_figure', 'n_keyword_with_mesh', 'n_mesh_matched', 'n_both',
            'n_available', 'agreement_any', 'agreement_any_wilson_lo', 'agreement_any_wilson_hi',
            'coverage_any', 'kappa_any', 'kappa_any_boot_lo', 'kappa_any_boot_hi',
            'agreement_major', 'coverage_major', 'kappa_major'}


class MappingTests(unittest.TestCase):
    def test_mapping_covers_every_figure_area(self):
        self.assertEqual(set(mc.load_mapping()), set(DOMAINS))

    def test_descriptor_regexes_are_anchored_and_case_insensitive(self):
        self.assertTrue(mc.matches('Electron microscopy', ['Microscopy, Electron, Scanning']))
        self.assertFalse(mc.matches('Electron microscopy', ['Microscopy, Fluorescence']))
        self.assertTrue(mc.matches('Immunology', ['t-lymphocytes']))
        self.assertFalse(mc.matches('Immunology', ['Microscopy, Immunoelectron']))
        self.assertTrue(mc.matches('Computational methods', ['Image Processing, Computer-Assisted']))
        self.assertFalse(mc.matches('Cancer', ['Cancer Survivors']))


class StatisticTests(unittest.TestCase):
    def test_wilson_interval(self):
        lo, hi = mc.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.236593, places=5)
        self.assertAlmostEqual(hi, 0.763407, places=5)
        self.assertTrue(math.isnan(mc.wilson(0, 0)[0]))

    def test_kappa(self):
        self.assertAlmostEqual(mc.kappa([30, 10, 5, 55]), 0.6808510638)
        self.assertAlmostEqual(mc.kappa([2, 0, 0, 2]), 1)
        self.assertTrue(math.isnan(mc.kappa([0, 0, 0, 4])))

    def test_mesh_descriptor_and_major_flag(self):
        record = {'meshHeadingList': {'meshHeading': [
            {'descriptorName': 'Brain', 'majorTopic_YN': 'N',
             'meshQualifierList': {'meshQualifier': [{'majorTopic_YN': 'Y'}]}},
            {'descriptorName': 'Neurons', 'majorTopic_YN': 'Y'}]}}
        self.assertEqual(mc.extract_mesh(record), (['Brain', 'Neurons'], ['Neurons']))
        self.assertEqual(mc.extract_mesh({}), ([], []))


class SamplingTests(unittest.TestCase):
    def test_draw_is_seeded_unique_and_weighted(self):
        frame = pd.DataFrame({'pmid': [str(i) for i in range(40)],
                              'stratum': ['rare'] * 4 + ['common'] * 36})
        a, design = mc.draw_sample(frame, target=20, seed=123, floor=5)
        b, _ = mc.draw_sample(frame, target=20, seed=123, floor=5)
        self.assertEqual(a.pmid.tolist(), b.pmid.tolist())
        self.assertEqual(len(a), 20)
        self.assertEqual(a.pmid.nunique(), 20)
        self.assertEqual(set(a.stratum), {'rare', 'common'})
        self.assertEqual(int(design['n'].sum()), 20)
        self.assertEqual(a[a.stratum == 'rare'].selection_probability.iloc[0], 1)
        self.assertAlmostEqual(float((1 / a.selection_probability).sum()), 40)

    def test_rarest_area_wins_the_stratum_when_counts_tie(self):
        frame = pd.DataFrame({'pmid': ['1', '2'], 'year': [2021, 2021], 'figure_row_count': [1, 1],
                              'figweight': [1.0, 1.0], 'Cancer': [True, False], 'Immunology': [True, True],
                              'Plant biology': [False, False]})
        assigned = mc.assign_strata(frame, ['Cancer', 'Immunology', 'Plant biology'])
        self.assertEqual(assigned.tolist(), ['Cancer', 'Immunology'])


class RequestTests(unittest.TestCase):
    def test_batches_are_sorted_and_bounded(self):
        frame = pd.DataFrame({'pmid': [str(i) for i in range(250)]})
        batches = mc.batches(frame)
        self.assertEqual([len(chunk) for chunk, _ in batches], [100, 100, 50])
        self.assertEqual([p for chunk, path in batches for p in chunk], sorted(frame.pmid))

    def test_cache_path_follows_the_shared_http_helper(self):
        from census._http import _cache_path
        params = mc.expected_params(['1', '2'])
        self.assertEqual(mc.cache_path(params), _cache_path(mc.SOURCE, mc.API, params))

    def test_request_shape_stays_stable(self):
        params = mc.expected_params(['1', '2'])
        self.assertEqual(params['resultType'], 'core')
        self.assertEqual(params['pageSize'], mc.BATCH)
        self.assertEqual(params['query'], '(EXT_ID:1 OR EXT_ID:2) AND SRC:MED')

    def test_fetch_rejects_a_response_from_another_batch(self):
        with self.assertRaises(ValueError):
            mc.check_response({'hitCount': 1, 'resultList': {'result': [
                {'id': '9', 'source': 'MED'}]}}, ['1'])


class OfflineTests(unittest.TestCase):
    def test_offline_fetch_refuses_a_missing_batch(self):
        frame = pd.DataFrame({'pmid': ['1', '2']})
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mc, 'cache_path', lambda params: Path(tmp) / 'absent.json'):
                with patch.object(mc, 'get_json', lambda *a, **k: calls.append(a)):
                    with self.assertRaises(RuntimeError) as caught:
                        mc.fetch(frame, offline=True)
        self.assertIn('offline', str(caught.exception))
        self.assertEqual(calls, [])


@unittest.skipUnless(PAPER_CSV.is_file(), 'run `python -m census.validation.mesh_check` first')
class PaperOutputTests(unittest.TestCase):
    def setUp(self):
        self.papers = pd.read_csv(PAPER_CSV, dtype={'pmid': str})

    def test_paper_file_carries_no_article_text(self):
        for column in self.papers.columns:
            low = column.lower()
            for banned in ('title', 'abstract', 'text', 'venue', 'descriptor'):
                self.assertNotIn(banned, low)
        for area in DOMAINS:
            self.assertIn(area, self.papers.columns)
            self.assertIn(f'mesh_any__{area}', self.papers.columns)
            self.assertIn(f'mesh_major__{area}', self.papers.columns)

    def test_medline_status_uses_the_record_and_never_invents_one(self):
        self.assertEqual(mc.medline_status({'isInMedline': 'Y'}), 'Y')
        self.assertEqual(mc.medline_status(
            {'subsetList': {'subset': [{'name': 'Index Medicus', 'code': 'IM'}]}}), 'Index Medicus')
        self.assertEqual(mc.medline_status({}), 'unknown')

    def test_identifiers_are_unique_and_flags_are_consistent(self):
        self.assertEqual(len(self.papers), self.papers.pmid.nunique())
        self.assertTrue(self.papers.pmid.str.fullmatch(r'[0-9]+').all())
        self.assertFalse(self.papers.is_in_medline.isna().any())
        self.assertTrue((self.papers.is_in_medline != '').all())
        for area in DOMAINS:
            any_flag, major_flag = self.papers[f'mesh_any__{area}'], self.papers[f'mesh_major__{area}']
            self.assertFalse((major_flag & ~any_flag).any(), area)


@unittest.skipUnless(AREA_CSV.is_file() and PAPER_CSV.is_file(),
                     'run `python -m census.validation.mesh_check` first')
class SummaryOutputTests(unittest.TestCase):
    def setUp(self):
        self.areas = pd.read_csv(AREA_CSV).set_index('area')
        self.papers = pd.read_csv(PAPER_CSV, dtype={'pmid': str})

    def test_summary_keeps_the_columns_the_pipeline_reads(self):
        self.assertTrue(CONSUMED <= set(self.areas.reset_index().columns))
        self.assertEqual(set(self.areas.index), set(DOMAINS))

    def test_counts_agree_with_the_paper_file(self):
        available = self.papers[self.papers.has_mesh]
        for area, row in self.areas.iterrows():
            self.assertEqual(int(row.n_available), len(available), area)
            self.assertEqual(int(row.n_keyword_sample), int(self.papers[area].sum()), area)
            self.assertEqual(int(row.n_keyword_with_mesh), int(available[area].sum()), area)
            self.assertEqual(int(row.n_mesh_matched), int(available[f'mesh_any__{area}'].sum()), area)
            self.assertEqual(int(row.n_both),
                             int((available[area] & available[f'mesh_any__{area}']).sum()), area)
        self.assertTrue((self.areas.agreement_major <= self.areas.agreement_any + 1e-12).all())
