# GSA contractor proposal travel estimate

Turn a proposal itinerary into GSA CONUS travel cost inputs with the [Allowances API trip calculator](https://www.allowancesapi.com/docs). This standalone Python example sends one request per scenario, exports daily and group amounts, and saves the original response for review. It does not implement its own per diem engine.

Use the GSA/FTR calculation model only when appropriate to your solicitation and approved estimating policy. These are **calculator-derived planning amounts**, not approved reimbursements, employee eligibility decisions, or guaranteed allowable costs. Allowances API is independent of the U.S. government.

## Quick start

Requires **Python 3.10 or later**, an Allowances API key, and network access. No packages, application checkout, database, or virtual environment are required. Download/copy this directory, then open a terminal in it.

Get a key through [registration](https://www.allowancesapi.com/register). Read [pricing](https://www.allowancesapi.com/pricing) for current plan/date access and request limits. The fixed sample uses **November 2026 (FY2027)** dates. It was verified against a local API with the development master test key acting as a paid-plan user on 2026-11-03; production and Sandbox access were not verified. Do not assume the fixed sample will remain eligible under your plan as time passes. Choose dates supported by your account and the published dataset. The script does not silently change dates or forecast unpublished rates.

In Bash, Zsh, or another POSIX shell, read the key without placing its value in command history:

```sh
printf 'API key: '
read -r ALLOWANCES_API_KEY
export ALLOWANCES_API_KEY
python3 proposal_estimate.py sample-proposal.json --output estimate/
unset ALLOWANCES_API_KEY
```

In PowerShell:

```powershell
$env:ALLOWANCES_API_KEY = Read-Host 'API key' -MaskInput
python proposal_estimate.py sample-proposal.json --output estimate/
Remove-Item Env:ALLOWANCES_API_KEY
```

`-MaskInput` requires PowerShell 7.1+. Use your normal environment/secret configuration instead if running an older shell. The key is read only from `ALLOWANCES_API_KEY`; the script does not load `.env` files. Never put the key in input JSON or shared output.

The output directory must not already exist. Pick a new name for each revision, for example `--output estimate-revision-2/`. The CLI defaults to `https://api.allowancesapi.com` and a 30-second request timeout. Use `--timeout 60` for a slower connection. `--base-url` accepts an HTTPS API origin, or HTTP loopback for local API testing; redirects are not followed with credentials. Only point it at an API you trust.

## What the example demonstrates

`sample-proposal.json` contains two independent scenarios:

- **Washington site visit:** three travelers, November 9–12, assumed room cost $200/night, and a lunch deduction on November 10 that the estimator has determined is required.
- **Washington/San Diego review:** two travelers, November 16–20, switching locality on November 18, assumed room costs $200 and $180/night respectively.

Destination IDs **75 (Washington)** and **34 (San Diego)** were verified through the local `GET /v1/gsa/destinations` endpoint on 2026-11-03. Display labels do not resolve locations. Review the destination's full area definition rather than assuming it describes only city limits.

Find replacement IDs by requesting the paginated destination catalog:

```sh
curl --fail-with-body 'https://api.allowancesapi.com/v1/gsa/destinations?limit=200&offset=0' \
  --header "X-API-Key: ${ALLOWANCES_API_KEY}"
```

Advance `offset` by 200 for subsequent pages. Select the correct destination using its name, state, county, and defined area. Trip locations accept `destination_id`, `zipcode`, or both, not city strings. A ZIP can be ambiguous; the script shows API candidates and requires you to select one explicitly before rerunning. Destination 0 identifies Standard CONUS; it is not an automatic fallback for a missing location.

## Input structure

```json
{
  "proposal": "Illustrative CONUS proposal travel",
  "scenarios": [
    {
      "id": "washington-site-visit",
      "travelers": 3,
      "trip": {
        "stops": [
          {
            "location": {"destination_id": 75},
            "arrival_date": "2026-11-09",
            "departure_date": "2026-11-12",
            "lodging_cost_per_night": 200
          }
        ],
        "deductible_meals": [
          {"date": "2026-11-10", "meals": ["lunch"]}
        ]
      }
    }
  ]
}
```

IDs must be unique, nonempty, non-personal strings; `travelers` must be a positive integer. `trip` follows the documented calculator request schema. The script forwards only `trip` to `POST /v1/gsa/calc/perdiem/trip`, forcing `verification_url=true`; proposal metadata and traveler count remain client-side. The API validates dates, stops, locators, meal deductions, and room costs.

Every traveler in a scenario shares the same itinerary, assumed room cost, and meal treatment. Split people into separate scenarios if those assumptions differ. Money is in USD. The client multiplies returned rounded totals by traveler count using decimal arithmetic; it never recalculates daily entitlement.

The calculator owns date-specific rate selection, first/last-day proration, seasonal and fiscal-year changes, meal deduction math, and actual-versus-cap lodging calculations. A stop represents the TDY locality, not simply the hotel location. Adjacent stops must share a boundary date; the arriving stop owns that day's locality. A return day has no lodging night. Use only caller-determined deductible meals: this example does not determine whether a furnished meal qualifies for deduction.

## Outputs and completeness

| File | Contents |
| --- | --- |
| `summary.csv` | One row per scenario: headcount, date/day/night counts, completeness, and per-traveler/group lodging, M&IE, total, and overage. |
| `daily.csv` | One row per scenario/day: resolved location, effective dates, source, fiscal year, proration, meal components, and lodging figures. Money columns are explicitly per traveler. |
| `rate-evidence.json` | Proposal/scenario metadata, endpoint, UTC retrieval timestamp, exact request body, complete parsed response, and overall status. No authentication headers. |
| `assumptions.md` | Room-cost assumptions, caller-submitted meal deductions, API notes, exclusions, status, and complete proposal totals when available. |

Although the endpoint names room costs `actual`, the input values here are **assumed proposal costs**, not incurred expenses. Lodging above the cap is reported separately as overage and excluded from the returned payable total. Excluded from this estimate: airfare, lodging taxes, ground transport, other costs, and escalation. The returned amounts alone do not establish contractor cost eligibility.

Try omitting lodging assumptions:

```sh
python3 proposal_estimate.py sample-missing-lodging.json --output estimate-missing/
```

The API returns lodging caps but null lodging/total amounts. These remain blank in CSV, and the proposal is marked **incomplete** with no proposal total; M&IE can still be shown. A blank on a return day also means no lodging night applies. Consult `lodging_night` and the evidence, not blank-to-zero spreadsheet conversions.

Exit codes: **0** = complete planning output; **2** = valid but incomplete planning output; **1** = input/API/export failure. Error runs preserve available evidence and the error in `rate-evidence.json`, but do not produce final CSVs or assumptions. A failed export may leave an internal `.exports/` directory; the failed evidence status is authoritative. No scenario is silently skipped. Fix the issue and rerun into a new directory. Requests are not automatically retried. For HTTP 401 check your key, for 403 check access, for 422 inspect structured validation/locality details, and for 429 check limits before retrying.

Saved responses preserve what was used even if published rates change. The response's `source_fingerprint` identifies source values but does not restore a historical snapshot. Keep `calculation_version`, request ID, source URLs, and API notes alongside your assumptions. Samples under `sample-output/` are **illustrative local API snapshots**, not live rate guarantees or production verification. Their loopback endpoint records the local verification environment.

CSV text starting with spreadsheet formula characters is prefixed with an apostrophe; original values remain in the JSON evidence.

## Offline tests

From this directory:

```sh
python3 -m unittest discover -s tests -v
```

Tests use recorded sample responses and synthetic variations, not a live API or private application imports. They verify request separation, one call per scenario, decimal aggregation, daily-field preservation, missing lodging, notes/evidence, credential-safe failures, and overwrite refusal. They do not implement or test a second per diem engine.

## Public repository handoff

Suggested repository name: **gsa-contractor-proposal-example**.

Description: “A runnable Python example that uses Allowances API's GSA trip calculator to prepare contractor proposal travel cost inputs with CSV summaries and saved evidence.”

Publication file list: `README.md`, `.gitignore`, `proposal_estimate.py`, `sample-proposal.json`, `sample-missing-lodging.json`, `sample-output/` (including its labeling README), and `tests/test_proposal_estimate.py`. These are self-contained; exclude generated estimates, `__pycache__`, credential files, private application code, and internal task files. Inspect the complete publication set again before publishing.

The owner/repository URL and license remain decisions for the publisher. **No open-source license has been granted by this example directory.** Add the chosen license before distributing it as open source. Repository creation and publication are separate human steps; no placeholder public URL or website backlink is included.

For more context, read [the API reference](https://www.allowancesapi.com/docs), [automating government allowance lookups](https://www.allowancesapi.com/learn/how-to-automate-government-allowance-lookups), and [the allowance source finder](https://www.allowancesapi.com/learn/federal-allowance-source-finder). The [overseas proposal guide](https://www.allowancesapi.com/learn/automate-overseas-allowances-contractor-proposals) covers a related workflow using different sources; this first runnable example is GSA CONUS only.
