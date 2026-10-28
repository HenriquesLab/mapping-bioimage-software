import unittest

from census._registry import alias_clause, load_registry, query_term


class QueryTermTests(unittest.TestCase):
    def test_wildcard_rule(self):
        self.assertEqual(query_term('QuPath'), 'QuPath*')
        self.assertEqual(query_term('QuPath', field='METHODS:'), 'METHODS:QuPath*')
        self.assertEqual(query_term('Fiji', exact=True), '"Fiji"')
        self.assertEqual(query_term('scikit-image'), '"scikit-image"')
        self.assertEqual(query_term('LAS X'), '"LAS X"')

    def test_registry_exact_aliases(self):
        reg = load_registry()
        self.assertNotIn('*', alias_clause(reg.by_id('cellpose')))  # census default: exact names
        self.assertIn('"Fiji"', alias_clause(reg.by_id('imagej'), wildcard=True))
        self.assertIn('ImageJ*', alias_clause(reg.by_id('imagej'), wildcard=True))
        amira = alias_clause(reg.by_id('amira'), wildcard=True)
        self.assertIn('"Amira"', amira)
        self.assertIn('"Avizo"', amira)
        self.assertNotIn('*', amira)
        self.assertNotIn('*', alias_clause(reg.by_id('cellpose'), wildcard=False))


    def test_census_queries_stay_exact(self):
        # wildcard_aliases is false: no census query path may carry a wildcard
        from census._registry import build_boolean_query
        from census.build import build_dataset_dl_in_tools as dlin
        from census.build.build_reporting_audit import frame_query
        reg = load_registry()
        self.assertEqual(
            build_boolean_query(reg.by_id('imagej'), reg.context_query, field='METHODS:'),
            '(METHODS:"ImageJ" OR METHODS:"ImageJ2" OR METHODS:"Fiji" OR METHODS:"FIJI") AND ((microscopy OR microscope) AND HAS_FT:Y)',
        )
        self.assertEqual(
            build_boolean_query(reg.by_id('qupath'), reg.context_query, field='METHODS:'),
            '(METHODS:"QuPath") AND ((microscopy OR microscope) AND HAS_FT:Y)',
        )
        for t in reg.tools:
            self.assertNotIn('*', build_boolean_query(t, reg.context_query))
            self.assertNotIn('*', frame_query(t, '(X)'))
            self.assertEqual(t.terms(), [f'"{a}"' for a in t.aliases])  # registry order, as cached
        tools = dlin.load_config().tools
        self.assertTrue(tools)
        for t in tools:
            self.assertNotIn('*', dlin.build_tool_query(t, reg.context_query, []))


    def test_revision_registry_entries_and_categories(self):
        from census._registry import VALID_CATEGORIES
        from census.figures.style import CATEGORY_COLOR, CATEGORY_LABEL
        from census.tables.make_si_tables import CATEGORY

        reg = load_registry()
        self.assertEqual(len(reg.tools), 33)
        imagepro = reg.by_id('imagepro')
        self.assertEqual(imagepro.category, 'commercial')
        self.assertEqual(imagepro.scope, 'counts')
        self.assertTrue(imagepro.in_aggregate)
        self.assertEqual(imagepro.aliases, [
            'Image-Pro', 'Image-Pro Plus', 'Image Pro Plus', 'ImagePro', 'Image-Pro Premier'
        ])
        nihimage = reg.by_id('nihimage')
        self.assertEqual(nihimage.category, 'general-platform')
        self.assertEqual(nihimage.aliases, ['NIH Image'])
        self.assertFalse(nihimage.in_aggregate)
        self.assertEqual(nihimage.exclude_aliases, [
            'NIH ImageJ', 'ImageJ', 'Image J', 'Image-J', 'ImageJ2', 'Image J2'
        ])
        from census._registry import build_boolean_query
        nih_query = build_boolean_query(nihimage, reg.context_query)
        self.assertIn('NOT', nih_query)
        self.assertIn('"NIH ImageJ"', nih_query)
        self.assertIn('"ImageJ"', nih_query)
        methods_query = build_boolean_query(nihimage, '', field='METHODS:')
        self.assertIn('METHODS:"ImageJ"', methods_query)
        self.assertIn('NOT', methods_query)
        from census.build.build_sensitivity import _methods
        self.assertIn('METHODS:"ImageJ"', _methods(nihimage))
        from census.build.build_methods_check import _field
        self.assertIn('METHODS:"ImageJ"', _field(nihimage, 'METHODS:'))
        from census.build.build_reporting_audit import frame_query
        self.assertIn('METHODS:"ImageJ"', frame_query(nihimage, reg.context_query))
        from census.build.build_reach_any import group_clause
        self.assertIn('NOT', group_clause([nihimage]))
        photoshop = reg.by_id('photoshop')
        self.assertEqual(photoshop.category, 'figure-preparation')
        self.assertFalse(photoshop.in_aggregate)
        self.assertEqual(photoshop.aliases, ['Adobe Photoshop', 'Photoshop'])
        self.assertIn('figure-preparation', VALID_CATEGORIES)
        self.assertIn('figure-preparation', CATEGORY_COLOR)
        self.assertIn('figure-preparation', CATEGORY_LABEL)
        self.assertIn('figure-preparation', CATEGORY)
        analysis = [t.id for t in reg.tools if t.in_aggregate and t.category != 'acquisition-suite']
        self.assertIn('imagepro', analysis)
        self.assertNotIn('nihimage', analysis)
        self.assertNotIn('photoshop', analysis)
        self.assertNotIn('*', alias_clause(imagepro))
        self.assertNotIn('*', alias_clause(nihimage))
        self.assertNotIn('*', alias_clause(photoshop))

if __name__ == '__main__':
    unittest.main()
