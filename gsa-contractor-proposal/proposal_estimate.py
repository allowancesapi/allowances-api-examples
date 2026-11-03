#!/usr/bin/env python3
"""Export GSA proposal planning inputs using the Allowances API trip calculator."""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ENDPOINT = '/v1/gsa/calc/perdiem/trip'
MONEY_FIELDS = ('lodging_payable', 'mie_payable', 'total_payable', 'lodging_overage')


class EstimateError(Exception):
	"""An actionable input, transport, or API failure."""


class NoRedirect(HTTPRedirectHandler):
	def redirect_request(self, req, fp, code, msg, headers, newurl):
		return None  # Do not forward credentials to a redirect target.


def write_json(path, value):
	path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def reject_constant(value):
	raise ValueError("Non-finite JSON number: " + value)


def load_proposal(path):
	try:
		proposal = json.loads(path.read_text(encoding='utf-8'), parse_constant=reject_constant)
	except (OSError, ValueError) as exc:
		raise EstimateError('Cannot read input as valid JSON.') from exc
	if not isinstance(proposal, dict) or not isinstance(proposal.get('proposal'), str) or not proposal['proposal'].strip():
		raise EstimateError('Input requires a nonempty proposal label.')
	scenarios = proposal.get('scenarios')
	if not isinstance(scenarios, list) or not scenarios:
		raise EstimateError('Input requires a nonempty scenarios list.')
	seen = set()
	for scenario in scenarios:
		if not isinstance(scenario, dict):
			raise EstimateError('Every scenario must be an object.')
		identifier = scenario.get('id')
		if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
			raise EstimateError('Scenario IDs must be nonempty, unique strings.')
		seen.add(identifier)
		if type(scenario.get('travelers')) is not int or scenario['travelers'] < 1:
			raise EstimateError('Each scenario requires a positive integer travelers count.')
		trip = scenario.get('trip')
		if not isinstance(trip, dict) or not isinstance(trip.get('stops'), list) or not trip['stops']:
			raise EstimateError('Each scenario requires a trip object with a nonempty stops list.')
	return proposal


def calculate(trip, key, base_url, timeout):
	request = Request(base_url.rstrip('/') + ENDPOINT, data=json.dumps(trip, allow_nan=False).encode('utf-8'),
		headers={'X-API-Key': key, 'Content-Type': 'application/json', 'Accept': 'application/json'})
	try:
		with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
			payload = json.load(response)
	except HTTPError as exc:
		try:
			message = json.dumps(json.loads(exc.read()), ensure_ascii=False)
		except (ValueError, OSError):
			message = 'No structured error details returned.'
		hints = {401: 'Check ALLOWANCES_API_KEY.', 403: 'Check plan and date access.',
			422: 'Review the input; select an explicit destination_id if ZIP candidates are returned.',
			429: 'Check request limits and wait before running again.'}
		raise EstimateError(f'HTTP {exc.code}. {hints.get(exc.code, "Check API availability and the response details.")} {message}') from None
	except (TimeoutError, URLError, OSError):
		raise EstimateError('API connection failed or timed out; check the endpoint and network, then rerun with a new output directory.') from None
	except ValueError:
		raise EstimateError('API returned invalid JSON.') from None
	if not isinstance(payload, dict) or any(name not in payload for name in ('trip', 'totals', 'days')):
		raise EstimateError('API response is missing trip, totals, or days; no estimate was produced.')
	return payload


def money(value, travelers=1):
	if value is None:
		return ''
	try:
		amount = Decimal(str(value))
		if not amount.is_finite():
			raise InvalidOperation
		return format(amount * travelers, '.2f')
	except (InvalidOperation, ValueError):
		raise EstimateError('API returned an invalid monetary value.') from None


def csv_file(path, fields, rows):
	with path.open('w', encoding='utf-8', newline='') as handle:
		writer = csv.DictWriter(handle, fieldnames=fields)
		writer.writeheader()
		for row in rows:
			# IDs/labels/locality text must remain inert when opened in a spreadsheet.
			writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for k, v in row.items()})


def export(proposal, evidence, output):
	summary, daily = [], []
	assumptions = [
		'# Proposal planning assumptions', '',
		'Calculator-derived planning amounts in USD, not approved reimbursements or guaranteed allowable costs.',
		'Use the GSA/FTR model only where appropriate to the solicitation and approved policy.',
		'Each scenario applies the same itinerary, assumed lodging cost, and meal treatment to every traveler.',
		'Room costs supplied as calculator actuals are proposal assumptions, not incurred expenses.',
		'Excluded: airfare, lodging taxes, ground transport, other costs, and escalation. Published rates are not forecasts.',
		'The API applies locality/date selection, proration, caps, and caller-determined meal deductions.',
		'A missing lodging amount is unknown, not zero. Resolve incomplete inputs before using a proposal total.', '',
	]
	for scenario, entry in zip(proposal['scenarios'], evidence['scenarios']):
		response = entry['response']
		totals, trip = response['totals'], response['trip']
		complete = totals['lodging_actuals_complete'] and all(totals[f] is not None for f in MONEY_FIELDS)
		row = {'scenario_id': scenario['id'], 'travelers': scenario['travelers'], 'status': 'complete' if complete else 'incomplete',
			**{f: trip[f] for f in ('start_date', 'end_date', 'days', 'nights')}}
		for field in MONEY_FIELDS:
			row['per_traveler_' + field] = money(totals[field])
			row['group_' + field] = money(totals[field], scenario['travelers'])
		summary.append(row)
		assumptions += [f'## Scenario {scenario["id"]}', '', f'Status: {row["status"]}. Travelers: {scenario["travelers"]}.', '']
		for index, stop in enumerate(entry['request']['stops'], 1):
			assumptions.append(f'- Stop {index}: {json.dumps(stop, ensure_ascii=False)}')
		assumptions += ['- Caller-determined meal deductions: ' + json.dumps(entry['request'].get('deductible_meals', [])),
			'- API notes: ' + json.dumps(response.get('notes', []), ensure_ascii=False), '']
		for day in response['days']:
			item = {'scenario_id': scenario['id'], 'travelers': scenario['travelers'],
				**{f: day[f] for f in ('date', 'rate_source', 'fiscal_year', 'per_diem_effective_date', 'mie_breakdown_effective_date', 'day_type')},
				'destination_id': day['locality']['destination_id'], 'locality': day['locality']['name'], 'county': day['locality']['county'],
				'mie_proration_factor': day['mie']['proration_factor'], 'deducted_meals': ', '.join(day['mie']['deducted_meals']),
				'lodging_night': day['lodging']['night']}
			for field in ('full_rate', 'prorated_rate', 'meal_deductions', 'payable'):
				item['per_traveler_mie_' + field] = money(day['mie'][field])
			for field, value in day['mie']['breakdown'].items():
				item['per_traveler_mie_breakdown_' + field] = money(value)
			for field in ('cap', 'actual', 'payable', 'overage'):
				item['per_traveler_lodging_' + ('assumed_cost' if field == 'actual' else field)] = money(day['lodging'].get(field))
			daily.append(item)
	complete = all(row['status'] == 'complete' for row in summary)
	assumptions += ['## Proposal status', '', 'Complete.' if complete else 'Incomplete: no proposal total is available.', '']
	if complete:
		for field in MONEY_FIELDS:
			total = sum((Decimal(row['group_' + field]) for row in summary), Decimal('0'))
			assumptions.append(f'- Proposal {field}: USD {money(total)}')
	csv_file(output / 'summary.csv', list(summary[0]), summary)
	if not daily:
		raise EstimateError('API returned no daily results; no complete estimate is available.')
	csv_file(output / 'daily.csv', list(daily[0]), daily)
	(output / 'assumptions.md').write_text('\n'.join(assumptions) + '\n', encoding='utf-8')
	evidence['status'] = 'complete' if complete else 'incomplete'


def run(proposal, output, key, base_url, timeout):
	try:
		output.mkdir(parents=True, exist_ok=False)
	except FileExistsError:
		raise EstimateError('Output directory already exists; choose a new directory.') from None
	evidence = {'proposal': proposal['proposal'], 'endpoint': base_url.rstrip('/') + ENDPOINT, 'status': 'in_progress', 'scenarios': []}
	try:
		for scenario in proposal['scenarios']:
			trip = {**scenario['trip'], 'verification_url': True}
			entry = {'scenario_id': scenario['id'], 'travelers': scenario['travelers'], 'request': trip,
				'requested_at': datetime.now(timezone.utc).isoformat()}
			evidence['scenarios'].append(entry)
			entry['response'] = calculate(trip, key, base_url, timeout)
			entry['retrieved_at'] = datetime.now(timezone.utc).isoformat()
		# Validate/export off to a temporary subdirectory so failed runs have no final CSVs.
		staging = output / '.exports'
		staging.mkdir()
		export(proposal, evidence, staging)
		for file in staging.iterdir():
			file.rename(output / file.name)
		staging.rmdir()
	except (EstimateError, OSError, KeyError, TypeError, ValueError) as exc:
		evidence['status'] = 'failed'
		evidence['error'] = str(exc).replace(key, '[REDACTED]')
		raise EstimateError('Estimate failed; inspect rate-evidence.json. ' + evidence['error']) from None
	finally:
		write_json(output / 'rate-evidence.json', evidence)
	return evidence['status']


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('input', type=Path)
	parser.add_argument('--output', required=True, type=Path)
	parser.add_argument('--base-url', default='https://api.allowancesapi.com', help='API origin; HTTP is allowed only on loopback for local testing.')
	parser.add_argument('--timeout', type=float, default=30)
	args = parser.parse_args(argv)
	key = os.environ.get('ALLOWANCES_API_KEY', '').strip()
	try:
		if not key:
			raise EstimateError('Set ALLOWANCES_API_KEY before running.')
		url = urlsplit(args.base_url)
		if (url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1'))) or not url.hostname or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
			raise EstimateError('--base-url must be an HTTPS origin (or HTTP loopback for local tests).')
		if not 0 < args.timeout <= 300:
			raise EstimateError('--timeout must be between 0 and 300 seconds.')
		proposal = load_proposal(args.input)
		status = run(proposal, args.output, key, args.base_url, args.timeout)
		print(f'Proposal {status}; see {args.output}/assumptions.md and rate-evidence.json.')
		return 0 if status == 'complete' else 2
	except (EstimateError, OSError, ValueError) as exc:
		print(str(exc).replace(key, '[REDACTED]') if key else str(exc), file=sys.stderr)
		return 1


if __name__ == '__main__':
	sys.exit(main())
