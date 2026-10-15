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
        for t in reg.tools:
            self.assertNotIn('*', build_boolean_query(t, reg.context_query))
            self.assertNotIn('*', frame_query(t, '(X)'))
            self.assertEqual(t.terms(), [f'"{a}"' for a in t.aliases])  # registry order, as cached
        tools = dlin.load_config().tools
        self.assertTrue(tools)
        for t in tools:
            self.assertNotIn('*', dlin.build_tool_query(t, reg.context_query, []))


if __name__ == '__main__':
    unittest.main()
