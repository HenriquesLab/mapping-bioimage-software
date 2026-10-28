"""Offline checks for reproducible identifier draws and optional pipeline steps."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class DrawTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('census.validation.draw_validation_samples'),
                             'validation drawing module is missing')
        from census.validation import draw_validation_samples
        self.draw = draw_validation_samples

    def test_seeded_draw_is_order_independent_without_replacement(self):
        frame = pd.DataFrame([{'stratum': 'a', 'tool_id': 'imagej', 'year': '2025',
                               'epmc_id': str(i), 'pmcid': ''} for i in range(20)])
        one, design = self.draw.draw(frame, {'a': 5}, 'recorded-string-seed', 'alias')
        two, _ = self.draw.draw(frame.iloc[::-1], {'a': 5}, 'recorded-string-seed', 'alias')
        pd.testing.assert_frame_equal(one, two)
        self.assertEqual(len(one), 5)
        self.assertEqual(one.epmc_id.nunique(), 5)
        self.assertEqual(design[0]['sampling_fraction'], 0.25)
        self.assertEqual(design[0]['seed'], 'recorded-string-seed-alias-a')
        census, _ = self.draw.draw(frame, {'a': 30}, 's', 'alias')
        self.assertEqual(len(census), 20)
        with self.assertRaises(ValueError):
            self.draw.draw(frame, {'a': -1}, 's', 'alias')

    def test_all_subcommands_write_identifiers_and_provenance_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = root / 'frame.csv'
            for command in self.draw.NAMES:
                strata = (['cellpose'] if command == 'cellpose' else self.draw.ALIAS_TOOLS if command == 'alias'
                          else list(self.draw.REGISTRY_PRECISION_TOOLS) if command == 'registry_precision'
                          else ['nihimage_historical'] if command == 'nihimage_historical'
                          else ['lex_pos', 'lex_neg'] if command == 'lexicon'
                          else list(json.loads(self.draw.PATTERNS.read_text())))
                id_command = command in ('cellpose', 'alias', 'registry_precision', 'nihimage_historical')
                pd.DataFrame([{'stratum': s,
                               'tool_id': 'nihimage' if command == 'nihimage_historical' else s if id_command else 'imagej',
                               'year': '2000' if command == 'nihimage_historical' else '2025',
                               'epmc_id': '' if id_command else str(i),
                               'pmcid': 'PMC' + str(i) if id_command else ''}
                              for s in strata for i in range(140)]).to_csv(frame, index=False)
                out = root / command
                self.draw.main([command, '--frame', str(frame), '--output-dir', str(out), '--seed', 'new-seed'])
                dest = out / (self.draw.NAMES[command] + '_items.csv')
                items = pd.read_csv(dest)
                self.assertEqual(list(items.columns), self.draw.COLUMNS)
                meta = json.loads(dest.with_suffix('.json').read_text())
                self.assertEqual(meta['seed'], 'new-seed')
                self.assertEqual(len(meta['frame_sha256']), 64)
                self.assertEqual(meta['historical_draw_recovered'], False)
                before = dest.read_bytes()
                with self.assertRaises(FileExistsError):
                    self.draw.main([command, '--frame', str(frame), '--output-dir', str(out)])
                self.assertEqual(dest.read_bytes(), before)

    def test_registry_precision_is_a_validation_command(self):
        self.assertIn('registry_precision', self.draw.NAMES)
        self.assertIn('nihimage_historical', self.draw.NAMES)

    def test_historical_nihimage_frame_covers_1995_to_2003_and_draws_all_if_short(self):
        def ids(query):
            year = query.rsplit('PUB_YEAR:', 1)[1]
            return [f'PMC{year}']

        with patch.object(self.draw, 'frame_pmcids', side_effect=ids):
            frame, meta = self.draw.build_frame('nihimage_historical')
        self.assertEqual(set(meta['queries']), {f'nihimage-{year}' for year in range(1995, 2004)})
        self.assertEqual(set(frame.stratum), {'nihimage_historical'})
        self.assertEqual(set(frame.tool_id), {'nihimage'})
        self.assertEqual(set(frame.year), {str(year) for year in range(1995, 2004)})
        self.assertTrue(all('OPEN_ACCESS:Y' in q and 'HAS_FT:Y' in q for q in meta['queries'].values()))
        self.draw.validate_frame(frame, 'nihimage_historical')
        sample, design = self.draw.draw(frame, {'nihimage_historical': 40}, 'historic-seed', 'nihimage_historical')
        self.assertEqual(len(sample), 9)
        self.assertEqual(design[0]['sampled'], 9)
        self.assertTrue(design[0]['census'])

    def test_registry_precision_builds_2024_2025_query_frames(self):
        def ids(query):
            year = '2024' if 'PUB_YEAR:2024' in query else '2025'
            return ['PMC' + year]
        with patch.object(self.draw, 'frame_pmcids', side_effect=ids):
            frame, meta = self.draw.build_frame('registry_precision')
        self.assertEqual(set(meta['queries']), {
            'imagepro-2025', 'nihimage-2024', 'nihimage-2025', 'photoshop-2025'
        })
        for key in ('nihimage-2024', 'nihimage-2025'):
            self.assertIn('"NIH ImageJ"', meta['queries'][key])
            self.assertIn('"Image J"', meta['queries'][key])
        self.assertEqual(set(frame[frame.tool_id == 'nihimage'].year), {'2024', '2025'})
        self.assertEqual(set(frame[frame.tool_id != 'nihimage'].year), {'2025'})
        self.assertEqual(set(frame.tool_id), set(self.draw.REGISTRY_PRECISION_TOOLS))
        self.draw.validate_frame(frame, 'registry_precision')

    def test_registry_precision_draws_40_per_package_without_replacement(self):
        rows = [dict(stratum=tool, tool_id=tool,
                     year='2024' if tool == 'nihimage' and i < 10 else '2025',
                     epmc_id='', pmcid=f'PMC{100000 + i}')
                for tool in self.draw.REGISTRY_PRECISION_TOOLS for i in range(60)]
        frame = pd.DataFrame(rows)
        self.draw.validate_frame(frame, 'registry_precision')
        sizes = {tool: 40 for tool in self.draw.REGISTRY_PRECISION_TOOLS}
        one, design = self.draw.draw(frame, sizes, 'precision-seed', 'registry_precision')
        two, _ = self.draw.draw(frame.iloc[::-1], sizes, 'precision-seed', 'registry_precision')
        pd.testing.assert_frame_equal(one, two)
        self.assertEqual(len(one), 120)
        self.assertEqual(one.groupby('tool_id').size().to_dict(), {tool: 40 for tool in sizes})
        self.assertEqual(one.groupby('tool_id').pmcid.nunique().to_dict(), {tool: 40 for tool in sizes})
        self.assertTrue(all(d['sampled'] == 40 for d in design))

    def test_corpus_frames_match_current_classifiers_and_scopes(self):
        corpus = pd.DataFrame([
            {'tool_id': 'imagej', 'year': 2025, 'epmc_id': '1', 'title': 'Deep learning in brain', 'abstract': ''},
            {'tool_id': 'matlab', 'year': 2025, 'epmc_id': '2', 'title': 'brain', 'abstract': ''},
            {'tool_id': 'imagej', 'year': 2025, 'epmc_id': '3', 'title': 'brain', 'abstract': ''},
            {'tool_id': 'imagej', 'year': 2020, 'epmc_id': '4', 'title': 'brain', 'abstract': ''}])
        lex = self.draw.corpus_frame(corpus, 'lexicon')
        self.assertEqual(set(lex.epmc_id), {'1', '3'})
        self.assertEqual(dict(zip(lex.epmc_id, lex.stratum)), {'1': 'lex_pos', '3': 'lex_neg'})
        domains = self.draw.corpus_frame(corpus, 'domains')
        self.assertEqual(set(domains[domains.stratum == 'Neuroscience'].epmc_id), {'1', '3'})

    def test_built_corpus_provenance_is_repository_relative(self):
        corpus = pd.DataFrame([
            {'tool_id': 'imagej', 'year': 2025, 'epmc_id': '1',
             'title': 'Deep learning in brain', 'abstract': ''}])
        with patch.object(self.draw.pd, 'read_csv', return_value=corpus), \
             patch.object(self.draw, 'sha256', return_value='fixture-hash'):
            for command in ('lexicon', 'domains'):
                frame, meta = self.draw.build_frame(command)
                self.assertFalse(frame.empty)
                self.assertEqual(meta['corpus'], 'data/processed/random_sample_2021_2025.csv.gz')

    def test_duplicates_and_incomplete_frames_rejected(self):
        frame = pd.DataFrame([dict(stratum='a',tool_id='t',year='2025',epmc_id='1',pmcid='')]*2)
        with self.assertRaises(ValueError):
            self.draw.draw(frame, {'a': 1}, 's', 'alias')
        with self.assertRaises(ValueError):
            self.draw.draw(frame.drop(columns='stratum'), {'a': 1}, 's', 'alias')

    def test_wrong_command_strata_years_tools_and_ids_are_rejected(self):
        valid = pd.DataFrame([dict(stratum='cellpose', tool_id='cellpose', year='2025', epmc_id='', pmcid='PMC123')])
        self.draw.validate_frame(valid, 'cellpose')
        for field, value in [('stratum', 'lex_pos'), ('tool_id', 'imagej'), ('year', '2024'), ('pmcid', 'bad')]:
            invalid = valid.copy()
            invalid[field] = value
            with self.assertRaises(ValueError):
                self.draw.validate_frame(invalid, 'cellpose')
        with self.assertRaises(ValueError):
            self.draw.validate_frame(valid, 'alias')

    def test_domain_pattern_parity_when_manuscript_is_available(self):
        import ast
        source = Path(__file__).resolve().parents[2] / 'MANUSCRIPT/FIGURES/_domains.py'
        if not source.exists():
            source = Path(__file__).resolve().parents[1] / 'census/figures/domains.py'
        if not source.exists():
            self.skipTest('standalone pipeline has no figure vocabulary reference')
        assignments = ast.parse(source.read_text()).body
        patterns = next(ast.literal_eval(n.value) for n in assignments if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'DOMAINS' for t in n.targets))
        saved = json.loads(self.draw.PATTERNS.read_text())
        self.assertEqual(list(saved.items()), list(patterns.items()))

    def test_probe_build_dl_consumes_rebuilt_literature(self):
        from census.validation import audit_reproducibility as probe
        self.assertTrue(hasattr(probe, 'rebuild_dl'), 'missing isolated rebuild helper')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            pd.DataFrame([{'count': 123}]).to_csv(out / 'literature_yearly.csv', index=False)
            with patch('census.build.build_dataset.build_dl') as builder:
                probe.rebuild_dl(out, 'registry')
            self.assertEqual(builder.call_args.args[1]['count'].tolist(), [123])

    def test_default_pipeline_has_no_optional_steps(self):
        from census import run_all
        self.assertEqual(run_all.optional_commands(False, [], 'seed'), [])
        cmds = run_all.optional_commands(True, ['cellpose', 'lexicon'], 'seed')
        self.assertEqual([c[1] for c in cmds],
                         ['census.build.build_reporting_audit', 'census.validation.validate_reporting_audit',
                          'census.validation.draw_validation_samples', 'census.validation.draw_validation_samples'])
        self.assertEqual(cmds[1][2:], ['sample'])
        self.assertEqual(cmds[2][2:], ['cellpose', '--seed', 'seed'])


if __name__ == '__main__':
    unittest.main()
