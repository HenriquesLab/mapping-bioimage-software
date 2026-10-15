import re
import unittest

import census.tables.make_si_tables as si


@unittest.skipUnless(si.SI.is_file(), 'Manuscript SI file ../MANUSCRIPT/02_SUPPLEMENTARY_INFO.md is not shipped')
class SITablesMatchTests(unittest.TestCase):
    def test_audit_area_has_four_columns_and_name_only_counts(self):
        table = si.TABLES['audit_area']()
        self.assertTrue(all(len(line.split('|')) == 6 for line in table.splitlines()))
        self.assertIn('| ImageJ/Fiji | 4 | 61 (352/577) | 61 (14/23) |', table)
        self.assertIn('<!-- TABLE:audit_area START -->', si.SI.read_text())

    def test_mesh_has_four_columns_and_weighted_agreement(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        import pandas as pd

        with TemporaryDirectory() as tmp:
            pd.DataFrame([{
                'area': 'Clinical and pathology', 'n_keyword_with_mesh': 683,
                'agreement_any': 0.116073, 'agreement_any_wilson_lo': 0.093508,
                'agreement_any_wilson_hi': 0.143224, 'kappa_any': 0.132542,
            }]).to_csv(Path(tmp) / 'mesh_check_2021_2025.csv', index=False)
            self.assertIn('mesh', si.TABLES)
            with patch.object(si, 'PROCESSED_DIR', Path(tmp)):
                table = si.TABLES['mesh']()
            self.assertTrue(all(len(line.split('|')) == 6 for line in table.splitlines()))
            self.assertIn('| Clinical and pathology | 683 | 12 (9-14) | 0.13 |', table)
        self.assertIn('<!-- TABLE:mesh START -->', si.SI.read_text())

    def test_generated_tables_match_the_supplement(self):
        # hand edits to a table block are lost on the next pipeline run; keep the generator authoritative
        text = si.SI.read_text()
        for key, fn in si.TABLES.items():
            m = re.search(rf'<!-- TABLE:{key} START -->\n(.*?)<!-- TABLE:{key} END -->', text, re.S)
            if m:
                with self.subTest(table=key):
                    self.assertEqual(m.group(1).strip(), fn().strip())


if __name__ == '__main__':
    unittest.main()
