"""Offline checks; recorded sample responses are fixtures, not live rate assertions."""
import copy
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import proposal_estimate as example

ROOT = Path(__file__).resolve().parents[1]


class ProposalTests(unittest.TestCase):
	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		self.addCleanup(self.temp.cleanup)
		self.output = Path(self.temp.name) / 'estimate'
		self.proposal = example.load_proposal(ROOT / 'sample-proposal.json')
		self.responses = [entry['response'] for entry in json.loads((ROOT / 'sample-output/complete/rate-evidence.json').read_text())['scenarios']]

	def run_fixture(self, proposal=None, responses=None):
		with patch.object(example, 'calculate', side_effect=responses or copy.deepcopy(self.responses)) as call:
			status = example.run(proposal or self.proposal, self.output, 'test-secret', 'https://api.example.test', 30)
		return status, call

	def test_requests_evidence_and_decimal_group_totals(self):
		responses = copy.deepcopy(self.responses)
		# Test non-integer cents without reproducing server entitlement calculations.
		responses[0]['totals']['total_payable'] = '896.17'
		status, call = self.run_fixture(responses=responses)
		self.assertEqual(status, 'complete')
		self.assertEqual(call.call_count, 2)
		for args in call.call_args_list:
			body = args.args[0]
			self.assertTrue(body['verification_url'])
			self.assertNotIn('travelers', body)
			self.assertNotIn('proposal', body)
			self.assertNotIn('id', body)
		evidence = json.loads((self.output / 'rate-evidence.json').read_text())
		self.assertEqual(evidence['scenarios'][0]['response'], responses[0])
		self.assertTrue(evidence['scenarios'][0]['retrieved_at'].endswith('+00:00'))
		self.assertNotIn('test-secret', (self.output / 'rate-evidence.json').read_text())
		with (self.output / 'summary.csv').open() as handle:
			rows = list(csv.DictReader(handle))
		self.assertEqual(rows[0]['group_total_payable'], '2688.51')
		self.assertEqual(rows[1]['group_total_payable'], '2315.00')
		self.assertIn('Proposal total_payable: USD 5003.51', (self.output / 'assumptions.md').read_text())

	def test_daily_dates_transition_and_meal_fields_are_preserved(self):
		self.run_fixture()
		with (self.output / 'daily.csv').open() as handle:
			rows = list(csv.DictReader(handle))
		transition = next(r for r in rows if r['date'] == '2026-11-18')
		self.assertEqual(transition['destination_id'], '34')
		meal = next(r for r in rows if r['date'] == '2026-11-10')
		self.assertEqual(meal['deducted_meals'], 'lunch')
		self.assertEqual(meal['per_traveler_mie_meal_deductions'], self.responses[0]['days'][1]['mie']['meal_deductions'])
		self.assertEqual(meal['per_diem_effective_date'], self.responses[0]['days'][1]['per_diem_effective_date'])
		self.assertIn('per_traveler_lodging_assumed_cost', meal)

	def test_missing_lodging_propagates_incomplete_without_a_proposal_total(self):
		proposal = example.load_proposal(ROOT / 'sample-missing-lodging.json')
		response = json.loads((ROOT / 'sample-output/missing-lodging/rate-evidence.json').read_text())['scenarios'][0]['response']
		status, _ = self.run_fixture(proposal, [response])
		self.assertEqual(status, 'incomplete')
		with (self.output / 'summary.csv').open() as handle:
			row = next(csv.DictReader(handle))
		self.assertEqual(row['group_total_payable'], '')
		self.assertEqual(row['per_traveler_lodging_payable'], '')
		self.assertNotEqual(row['group_mie_payable'], '')
		self.assertNotIn('Proposal total_payable:', (self.output / 'assumptions.md').read_text())

	def test_later_error_preserves_earlier_evidence_but_no_final_csvs(self):
		with self.assertRaises(example.EstimateError):
			self.run_fixture(responses=[self.responses[0], example.EstimateError('HTTP 403: test-secret')])
		evidence = json.loads((self.output / 'rate-evidence.json').read_text())
		self.assertEqual(evidence['status'], 'failed')
		self.assertEqual(evidence['scenarios'][0]['response'], self.responses[0])
		self.assertNotIn('test-secret', json.dumps(evidence))
		self.assertFalse(list(self.output.glob('*.csv')))
		self.assertFalse((self.output / 'assumptions.md').exists())

	def test_one_incomplete_scenario_suppresses_proposal_total(self):
		responses = copy.deepcopy(self.responses)
		responses[1]['totals'].update(lodging_payable=None, total_payable=None, lodging_overage=None, lodging_actuals_complete=False)
		status, _ = self.run_fixture(responses=responses)
		self.assertEqual(status, 'incomplete')
		self.assertNotIn('Proposal total_payable:', (self.output / 'assumptions.md').read_text())

	def test_invalid_response_export_has_no_final_estimate(self):
		responses = copy.deepcopy(self.responses)
		responses[1]['days'] = [{'date': '2026-11-16'}]
		with self.assertRaises(example.EstimateError):
			self.run_fixture(responses=responses)
		self.assertEqual(json.loads((self.output / 'rate-evidence.json').read_text())['status'], 'failed')
		self.assertFalse(list(self.output.glob('*.csv')))

	def test_cli_errors_redact_key(self):
		stderr = io.StringIO()
		with patch.dict(os.environ, {'ALLOWANCES_API_KEY': 'test-secret'}), patch.object(example, 'calculate', side_effect=example.EstimateError('HTTP 403 test-secret')), redirect_stderr(stderr):
			code = example.main([str(ROOT / 'sample-proposal.json'), '--output', str(self.output)])
		self.assertEqual(code, 1)
		self.assertNotIn('test-secret', stderr.getvalue())
		self.assertIn('REDACTED', stderr.getvalue())

	def test_existing_output_refused_before_any_api_call(self):
		self.output.mkdir()
		marker = self.output / 'keep.txt'
		marker.write_text('keep')
		with patch.object(example, 'calculate') as call, self.assertRaises(example.EstimateError):
			example.run(self.proposal, self.output, 'secret', 'https://api.example.test', 30)
		call.assert_not_called()
		self.assertEqual(marker.read_text(), 'keep')

	def test_small_wrapper_validation(self):
		variants = []
		duplicate = copy.deepcopy(self.proposal)
		duplicate['scenarios'][1]['id'] = duplicate['scenarios'][0]['id']
		variants.append(duplicate)
		for count in (0, -1, True, 1.5):
			variant = copy.deepcopy(self.proposal)
			variant['scenarios'][0]['travelers'] = count
			variants.append(variant)
		variants.extend([{}, {'proposal': 'x', 'scenarios': []}])
		path = Path(self.temp.name) / 'input.json'
		for variant in variants:
			with self.subTest(variant=variant):
				path.write_text(json.dumps(variant))
				with self.assertRaises(example.EstimateError):
					example.load_proposal(path)
		for raw in ('{', '{"proposal": NaN}'):
			path.write_text(raw)
			with self.assertRaises(example.EstimateError):
				example.load_proposal(path)

	def test_missing_key_cli_is_useful_and_creates_no_output(self):
		result = subprocess.run([sys.executable, str(ROOT / 'proposal_estimate.py'), str(ROOT / 'sample-proposal.json'), '--output', str(self.output)], env={k:v for k,v in os.environ.items() if k != 'ALLOWANCES_API_KEY'}, capture_output=True, text=True)
		self.assertEqual(result.returncode, 1)
		self.assertIn('ALLOWANCES_API_KEY', result.stderr)
		self.assertFalse(self.output.exists())

	def test_incomplete_cli_exit_is_distinct(self):
		with patch.dict(os.environ, {'ALLOWANCES_API_KEY': 'test-secret'}), patch.object(example, 'run', return_value='incomplete'), redirect_stdout(io.StringIO()):
			self.assertEqual(example.main([str(ROOT / 'sample-proposal.json'), '--output', str(self.output)]), 2)

	def test_api_errors_include_structured_candidates_and_limit_access_hints(self):
		for status in (401, 403, 422, 429, 503):
			with self.subTest(status=status):
				body = json.dumps({'detail': {'code': 'ambiguous_locality', 'context': {'candidates': [{'destination_id': 34}]}}}).encode()
				error = HTTPError('https://api.example.test', status, 'API error', {}, io.BytesIO(body))
				with patch.object(example, 'build_opener') as opener:
					opener.return_value.open.side_effect = error
					with self.assertRaises(example.EstimateError) as raised:
						example.calculate({}, 'secret', 'https://api.example.test', 30)
				self.assertIn('HTTP ' + str(status), str(raised.exception))
				self.assertIn('destination_id', str(raised.exception))

	def test_network_timeout_and_invalid_response(self):
		for error in (TimeoutError(), URLError('offline')):
			with patch.object(example, 'build_opener') as opener:
				opener.return_value.open.side_effect = error
				with self.assertRaisesRegex(example.EstimateError, 'connection failed or timed out'):
					example.calculate({}, 'secret', 'https://api.example.test', 1)
		for raw in (b'not JSON', b'{}'):
			with patch.object(example, 'build_opener') as opener:
				opener.return_value.open.return_value = io.BytesIO(raw)
				with self.assertRaises(example.EstimateError):
					example.calculate({}, 'secret', 'https://api.example.test', 1)

	def test_notes_and_no_credential_forwarding_on_redirect(self):
		responses = copy.deepcopy(self.responses)
		responses[0]['notes'] = ['Review the meal deduction assumptions.']
		self.run_fixture(responses=responses)
		self.assertIn('Review the meal deduction assumptions.', (self.output / 'assumptions.md').read_text())
		self.assertIsNone(example.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.test'))

	def test_money_and_csv_text(self):
		self.assertEqual(example.money('0.29', 3), '0.87')
		self.assertEqual(example.money(None, 3), '')
		with self.assertRaises(example.EstimateError):
			example.money('NaN')
		path = Path(self.temp.name) / 'text.csv'
		example.csv_file(path, ['scenario'], [{'scenario': '=1+1'}])
		with path.open() as handle:
			self.assertEqual(next(csv.DictReader(handle))['scenario'], "'=1+1")


if __name__ == '__main__':
	unittest.main()
