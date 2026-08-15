# the budget

Local constraint engine. Tells you what you can spend today.

The math is a port of the [What If Wallet](https://github.com/randomchaos7800-hub/whatifwallet) iOS engine. WIW stays the phone app. This is the web product.

> If your nut is $2,000 and you have $1,400, what can you spend today — and what cascades if you skip a bill?

## What it does

- Recurring income and bills as templates (weekly, bi-weekly, 1st & 15th, month-end, yearly)
- 365-day deterministic projection
- **Spendable today** = largest one-time spend that stays above the safety floor
- Skip once / stop a bill without corrupting the baseline
- Scenario overlays (Job Loss actually stops income — the iOS scenario did not)
- CSV import + recurring detection. Proposals only. Nothing auto-joins the model.
- Derived balance from an anchor + ledger
- Nightly job crystallizes past scheduled transactions so the number does not go stale

No bank logins. No cloud. SQLite file on disk.

## Run

```bash
cd ~/repos/the-budget
python3 -m budget serve
# http://127.0.0.1:8787
```

Load the demo household from the Import tab, or paste a bank CSV.

```bash
python3 -m unittest discover -s tests -v
python3 -m budget demo
python3 -m budget nightly
```

Cron (automation):

```
15 5 * * * cd /home/dino/repos/the-budget && /usr/bin/python3 -m budget nightly >> /home/dino/repos/the-budget/data/nightly.log 2>&1
```

Env: `BUDGET_DB`, `BUDGET_HOST`, `BUDGET_PORT`.

## Architecture

```
BaselineTemplate     Recurring income/expense rules (truth)
SimulationState      Non-destructive overrides (skip once / skip forever)
ProjectionEngine     Pure deterministic math → daily balances
SpendableToday       Binary search on a one-time spend
Ledger + Anchor      Reality layer; nightly crystallizes the past
CSV detect           Proposes templates; user confirms
```

Engine port lives in `budget/engine.py`. Tests in `tests/` are the WIW unit tests translated.

## Not this

- Not Mint/YNAB. No bank aggregation.
- No auto-approve of detected bills.
- No probabilistic forecast.

## License

MIT. Engine origin: WIW iOS. Product name: the budget.
