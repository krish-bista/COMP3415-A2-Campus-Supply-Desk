# CR-01 prediction recorded before implementation

Recorded on November 7, 2026, after the three refactorings and separate defect fixes.

## Expected behavior change

Add express to the service API, individual commands, and menu. Express costs
1200 cents on every order, including orders eligible for free standard delivery.
Student discounts still apply only to merchandise. Existing pickup and standard
delivery rules, validation, stock, history, and cancellation remain in force.

## Expected files and methods

- supplydesk/service.py: extend fulfillment validation and the delivery fee branch
  in _prepare_order, and add a named express fee.
- supplydesk/cli.py: include express in --fulfillment choices and explain the fee.
- supplydesk/menu.py: make express and its fee visible in the fulfillment prompt.
- README.md and FUNCTIONAL_SPEC.md: document the accepted option and pricing.
- tests/test_express.py: add CR-01 acceptance tests.
- tests/test_service.py and tests/test_interfaces.py: rerun unchanged regressions.

No storage schema change is expected. Orders already store fulfillment, delivery,
discount, items, and total as a snapshot. JsonStore can persist the additional string
using the existing schema version 1.

## Planned verification

- CR examples: notebook:2 regular express = 2200; hoodie:2 student express = 8400;
  hoodie:3 regular standard = 12000 and express = 13200.
- Express remains 1200 below, at, and above the standard free-delivery threshold.
- Discount boundaries and half-cent rounding remain correct for express.
- Quote and placed order agree, stock changes only on placement, IDs advance normally.
- Lookup, reopen, history, cancellation, and a second cancellation preserve snapshots.
- Invalid customer, quantity, stock, and unsupported fulfillment requests are rejected.
- Commands and menu can quote/place express, show the fee, and preserve default pickup.
- Existing schema version 1 pickup/delivery saves still reopen.
