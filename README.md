# What If Wallet (web)

Fork of the [What If Wallet](https://github.com/randomchaos7800-hub/whatifwallet) iOS engine. Same deterministic math. Web surface. Automation first.

The phone app's engine is solid. Friction was the surface: manual balance, manual templates, too many tabs. This fork keeps `ProjectionEngine` / `RecurrenceEngine` / skip semantics and makes **Spendable Today** the product.

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
cd ~/repos/whatifwallet-web
python3 -m whatifwallet serve
# http://127.0.0.1:8787
```

Load the demo household from the Import tab, or paste a bank CSV.

```bash
python3 -m unittest discover -s tests -v
python3 -m whatifwallet demo
python3 -m whatifwallet nightly
```

Cron (automation):

```
15 5 * * * cd /home/dino/repos/whatifwallet-web && /usr/bin/python3 -m whatifwallet nightly >> /home/dino/repos/whatifwallet-web/data/nightly.log 2>&1
```

Env: `WHATIFWALLET_DB`, `WHATIFWALLET_HOST`, `WHATIFWALLET_PORT`.

## Architecture

```
BaselineTemplate     Recurring income/expense rules (truth)
SimulationState      Non-destructive overrides (skip once / skip forever)
ProjectionEngine     Pure deterministic math → daily balances
SpendableToday       Binary search on a one-time spend
Ledger + Anchor      Reality layer; nightly crystallizes the past
CSV detect           Proposes templates; user confirms
```

Engine port lives in `whatifwallet/engine.py`. Tests in `tests/` are the iOS unit tests translated.

## Not this

- Not Mint/YNAB. No bank aggregation.
- No auto-approve of detected bills.
- No probabilistic forecast.

## License

MIT. Engine origin: Dino Vitale / What If Wallet iOS.
