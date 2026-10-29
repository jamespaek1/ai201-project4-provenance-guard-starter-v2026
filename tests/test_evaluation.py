"""Narrow evaluator checks; no service or model calls, no measured results."""
import unittest
from unittest.mock import patch

import run_eval
import scenarios


def result(guess='unsure', score=.5, status=200):
    return {'http_status': status, 'response': {'guess': guess, 'confidence': score}}


class EvaluationVerdictTests(unittest.TestCase):
    def test_missing_http_results_cannot_be_a_false_positive_pass(self):
        human = [result('human', .1) for _ in range(20)]
        ai = [result('ai', .8) for _ in range(20)]
        c1, c2 = run_eval.corpus_metrics(human, ai)
        self.assertTrue(c1['passed'])
        self.assertTrue(c2['passed'])
        human[-1] = result(status=429)
        c1, c2 = run_eval.corpus_metrics(human, ai)
        self.assertFalse(c1['passed'])
        self.assertFalse(c2['passed'])
        self.assertIsNone(c2['mean_gap'])

    def test_actual_targets_not_generous_readings(self):
        human = [result('ai' if i < 2 else 'unsure', .5) for i in range(20)]
        ai = [result('unsure', .69) for _ in range(20)]
        c1, c2 = run_eval.corpus_metrics(human, ai)
        self.assertEqual(c1['false_positives'], 2)
        self.assertFalse(c1['passed'])
        self.assertLess(c2['mean_gap'], .20)
        self.assertFalse(c2['passed'])
        exact = [result('unsure', .7) for _ in range(20)]
        _, exact_c2 = run_eval.corpus_metrics(human, exact)
        self.assertTrue(exact_c2['passed'])
        self.assertEqual(exact_c2['mean_gap'], .20)

    def test_numeric_coverage_cannot_replace_real_text_coverage(self):
        actual = [result('human', .1), result('unsure', .5), result('ai', .95)]
        measured = run_eval.coverage(actual)
        self.assertTrue(measured['passed'])
        self.assertEqual(len(measured['grid_points']), 1001)
        self.assertTrue(all(v['rejected'] for v in measured['invalid_scores']))
        incomplete = run_eval.coverage([result('unsure', .5)] * 7)
        self.assertFalse(incomplete['passed'])

    def test_bad_input_matrix_keeps_both_creator_variants_and_both_encodings(self):
        cases = scenarios.bad_input_cases('test', 'known-id')
        self.assertEqual(len(cases), 17)
        names = {c['name'] for c in cases}
        self.assertIn('blank_creator', names)
        self.assertIn('long_creator', names)
        self.assertEqual(sum(c.get('chunked', False) for c in cases), 2)
        for case in cases[-4:]:
            self.assertGreater(len(case['raw']), 64 * 1024)
            self.assertEqual(case['expected'], 413)
        appeal = next(c for c in cases if c['name'] == 'blank_appeal_reason')
        self.assertEqual(appeal['json']['content_id'], 'known-id')

    def test_incomplete_trial_report_cannot_say_met(self):
        report = {'label': 'test', 'trials': [{'criteria': [
            {'criterion': i, 'passed': True, 'metric': 'observed'} for i in range(1, 6)]}]}
        rendered = run_eval.markdown(report)
        self.assertEqual(rendered.count('| MISSED |'), 5)
        self.assertNotIn('| MET |', rendered)


if __name__ == '__main__':
    unittest.main()
