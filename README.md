# Allowances API examples: government per diem and travel rates

Runnable examples for integrating **U.S. government per diem and allowance rates** into applications with [Allowances API](https://www.allowancesapi.com/). Start with a Python contractor proposal example that uses the **GSA CONUS trip calculator** to produce travel cost inputs, CSV summaries, and saved rate evidence.

These examples are for developers building expense, travel, ERP, finance, and contractor proposal workflows. Each example includes its own setup instructions, sample inputs, and outputs so you can understand the integration before making an API request.

[Browse the API reference](https://www.allowancesapi.com/docs) · [Get an API key](https://www.allowancesapi.com/register) · [Check plans and historical access](https://www.allowancesapi.com/pricing)

## Available examples

| Example | Language | What you can build |
| --- | --- | --- |
| [GSA contractor proposal travel estimate](gsa-contractor-proposal/README.md) | Python 3.10+; standard library only | Turn single-destination and multi-stop CONUS itineraries into per-traveler and group travel cost inputs using the GSA trip calculator. Export daily calculations, scenario totals, assumptions, and original API responses. |

The runnable example currently covers **GSA CONUS travel**. DTMO and DSSR are part of the wider Allowances API service; this repository does not yet include runnable examples for those sources.

## Quick start: calculate GSA proposal travel costs in Python

You need Python 3.10 or later, an Allowances API key, and network access for live requests. No Python packages or database are required.

1. Download this repository or clone it:

   ```sh
   git clone https://github.com/allowancesapi/allowances-api-examples.git
   cd allowances-api-examples/gsa-contractor-proposal
   ```

2. [Create an account and obtain an API key](https://www.allowancesapi.com/register). In Bash or Zsh, set the key for this terminal session without putting its value in the command itself:

   ```sh
   printf 'API key: '
   read -r ALLOWANCES_API_KEY
   export ALLOWANCES_API_KEY
   ```

3. Review [sample-proposal.json](gsa-contractor-proposal/sample-proposal.json), then run:

   ```sh
   python3 proposal_estimate.py sample-proposal.json --output estimate/
   ```

4. Open `estimate/assumptions.md` and `estimate/summary.csv`. Keep `estimate/rate-evidence.json` with your estimate so a reviewer can inspect the requests, responses, effective dates, and available official source links.

The sample uses **Washington and San Diego in November 2026**. Choose dates supported by your plan and the published dataset; the script does not change dates automatically or forecast future rates. See [pricing](https://www.allowancesapi.com/pricing) for current access limits. Use a new output directory for each run; existing output directories are not overwritten.

For PowerShell setup, input details, error handling, and local testing, follow the [full example guide](gsa-contractor-proposal/README.md).

## How the GSA trip calculator example works

The example sends one authenticated request per travel scenario to:

```http
POST https://api.allowancesapi.com/v1/gsa/calc/perdiem/trip
X-API-Key: YOUR_API_KEY
Content-Type: application/json
```

Each scenario describes temporary-duty stops, travel dates, an optional nightly room-cost assumption, caller-determined meal deductions, and a traveler count. Locations use GSA destination IDs or supported ZIP codes. The sample includes both a single-destination trip and a contiguous multi-stop trip.

The **API** selects the applicable daily GSA rates and calculates lodging caps, lodging overages, first/last-day meals and incidental expenses (M&IE), and meal deductions. The **Python script** multiplies the returned totals by traveler count using decimal arithmetic and exports the results. All travelers within a scenario share the same itinerary and assumptions.

Room costs in this example are proposal assumptions supplied to the calculator's actual-cost field. The output is a planning input; the solicitation and approved estimating policy determine how it should be used.

### Output files

| File | What it contains |
| --- | --- |
| `summary.csv` | Per-traveler and group lodging, M&IE, total amounts, overages, and completeness for each scenario. |
| `daily.csv` | Daily locality, source, fiscal year, effective dates, meal calculations, and lodging figures. |
| `rate-evidence.json` | Request bodies and complete responses, UTC timestamps, calculation version, source fingerprint, request IDs, and available verification URLs. |
| `assumptions.md` | Input assumptions, API notes, excluded costs, completeness, and proposal totals when available. |

**Preview the output without an API key:** [complete estimate](gsa-contractor-proposal/sample-output/complete/summary.csv), [daily breakdown](gsa-contractor-proposal/sample-output/complete/daily.csv), [saved evidence](gsa-contractor-proposal/sample-output/complete/rate-evidence.json), and [assumptions](gsa-contractor-proposal/sample-output/complete/assumptions.md).

These are [illustrative snapshots from local API verification](gsa-contractor-proposal/sample-output/README.md), not live rate guarantees. The saved source fingerprint identifies source values; it does not restore a past dataset.

### What happens when lodging costs are unknown?

Run the [missing-lodging sample](gsa-contractor-proposal/sample-missing-lodging.json):

```sh
python3 proposal_estimate.py sample-missing-lodging.json --output estimate-missing/
```

The calculator can return nightly caps and M&IE while lodging and total amounts remain unknown. The example preserves those missing values and marks the proposal **incomplete**, rather than treating them as zero or inventing a payable total. [View the incomplete sample output](gsa-contractor-proposal/sample-output/missing-lodging/assumptions.md).

## Government rate sources and API coverage

Allowances API provides normalized JSON access to published government rate data, with location-based and effective-date-aware lookups. The service brings together three source families:

| Source | Data family |
| --- | --- |
| **GSA — General Services Administration** | Continental U.S. (CONUS) per diem, including lodging and meals and incidental expenses. Used by the runnable example in this repository. |
| **DTMO — Defense Travel Management Office** | Department of Defense outside-CONUS (OCONUS) per diem rates. |
| **DSSR — Department of State Standardized Regulations** | Foreign per diem and overseas allowances, including post allowance (COLA), living quarters allowance (LQA), hardship, and danger pay. |

Select the source required by your workflow; overseas destinations can appear in more than one system. Historical availability depends on the source, published data, endpoint, and subscription. See the [API documentation](https://www.allowancesapi.com/docs) for supported requests and response fields.

Allowances API is an independent service and is **not affiliated with any U.S. government agency**. Retrieving a rate or calculated amount does not establish employee eligibility, contractor cost allowability, or approval. The GSA example excludes airfare, lodging taxes, ground transport, other costs, and escalation.

## Learn more

- [Automate government allowance lookups in your application](https://www.allowancesapi.com/learn/how-to-automate-government-allowance-lookups) — replace manual rate maintenance with an API workflow.
- [Federal allowance source finder](https://www.allowancesapi.com/learn/federal-allowance-source-finder) — identify the appropriate government rate source.
- [Automate overseas allowances for contractor proposals](https://www.allowancesapi.com/learn/automate-overseas-allowances-contractor-proposals) — a related workflow using overseas sources; the runnable example here is CONUS only.
- [Connect an AI assistant to government travel rates](https://www.allowancesapi.com/learn/connect-ai-assistant-government-travel-rates) — retrieve rate inputs through MCP tools.
- [Allowances API MCP server setup](https://www.allowancesapi.com/mcp-server) — configure supported AI clients. The Python example itself uses REST and does not require an MCP client.

## Run the offline tests

From the repository root:

```sh
python3 -m unittest discover -s gsa-contractor-proposal/tests -v
```

Tests use recorded sample responses and synthetic variations. They require no API key or network connection and check request construction, decimal aggregation, missing inputs, exports, and error handling.

Keep API keys out of source files, input JSON, and shared output. Use fictional itineraries when sharing examples or reporting an issue. A repository license has not yet been added; review licensing before redistributing the code.
