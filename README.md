# Campus Supply Desk

Requires Python 3.10 or newer. No extra packages are needed.

## Run

From the project folder:

```sh
python -m supplydesk
```

The menu supports viewing stock, quotes, orders, history, lookup, and cancellation.
Press Enter at the customer and fulfillment prompts for regular and pickup.
The menu asks for confirmation before placement and cancellation.

## Run tests

```sh
python -m unittest discover -s tests -v
```

Expected result: 49 tests, OK. Tests use temporary save files.

## Express delivery

Pickup is free. Standard delivery costs CAD $6 and is free when merchandise
after discounts reaches CAD $100. Express always costs CAD $12.
Student discounts apply to merchandise only.

```sh
python -m supplydesk quote --customer student --fulfillment express --item hoodie:2
```

Expected total: 8400 cents (CAD $84). Quotes do not reserve stock or create orders.
Individual place and cancel commands act immediately.

## Saved data

The default save is .supplydesk/state.json. To use a separate practice file:

```sh
python -m supplydesk --data .supplydesk/practice.json
```

See FUNCTIONAL_SPEC.md for the application requirements.
