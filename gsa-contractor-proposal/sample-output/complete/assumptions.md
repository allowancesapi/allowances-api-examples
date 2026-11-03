# Proposal planning assumptions

Calculator-derived planning amounts in USD, not approved reimbursements or guaranteed allowable costs.
Use the GSA/FTR model only where appropriate to the solicitation and approved policy.
Each scenario applies the same itinerary, assumed lodging cost, and meal treatment to every traveler.
Room costs supplied as calculator actuals are proposal assumptions, not incurred expenses.
Excluded: airfare, lodging taxes, ground transport, other costs, and escalation. Published rates are not forecasts.
The API applies locality/date selection, proration, caps, and caller-determined meal deductions.
A missing lodging amount is unknown, not zero. Resolve incomplete inputs before using a proposal total.

## Scenario washington-site-visit

Status: complete. Travelers: 3.

- Stop 1: {"location": {"destination_id": 75}, "arrival_date": "2026-11-09", "departure_date": "2026-11-12", "lodging_cost_per_night": 200}
- Caller-determined meal deductions: [{"date": "2026-11-10", "meals": ["lunch"]}]
- API notes: []

## Scenario washington-san-diego-review

Status: complete. Travelers: 2.

- Stop 1: {"location": {"destination_id": 75}, "arrival_date": "2026-11-16", "departure_date": "2026-11-18", "lodging_cost_per_night": 200}
- Stop 2: {"location": {"destination_id": 34}, "arrival_date": "2026-11-18", "departure_date": "2026-11-20", "lodging_cost_per_night": 180}
- Caller-determined meal deductions: []
- API notes: []

## Proposal status

Complete.

- Proposal lodging_payable: USD 3320.00
- Proposal mie_payable: USD 1683.00
- Proposal total_payable: USD 5003.00
- Proposal lodging_overage: USD 0.00
