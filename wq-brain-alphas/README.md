# wq-brain-alphas

A small research pipeline for WorldQuant BRAIN. It simulates alpha expressions through the BRAIN API, stores every result in SQLite, and lists the alphas that pass the submission checks, with a hint for fixing each one that fails. Submitting stays a manual step.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then fill in your BRAIN login
```

Python 3.11 or newer (uses `tomllib`).

## Try it offline first

`--dry-run` uses a fake client with random metrics, so you can learn the commands without using your simulation quota.

```bash
python run.py --dry-run simulate alphas/starter.txt
python run.py report --all
```

## Real workflow

```bash
# 1. Run the starter ideas with the default settings in settings.toml
python run.py simulate alphas/starter.txt

# 2. Re-run with different settings (each settings combination is stored separately)
python run.py simulate alphas/starter.txt --set decay=10 --set neutralization=MARKET

# 3. Get field ids from a dataset, then sweep templates across them
python run.py fields fundamental6 -o fields.txt
python run.py sweep alphas/templates.txt fields.txt --windows 20 60 250 --limit 30

# 4. Look at what passes, best fitness first
python run.py report            # passing only
python run.py report --all      # everything, with failed checks or a fix hint

# 5. Check the alpha in the BRAIN web UI, then submit
python run.py submit <ALPHA_ID>
```

Expressions already run with the same settings are skipped, so you can stop with Ctrl+C and resume later.

## Files

| File | Purpose |
|---|---|
| `brain/client.py` | BRAIN API: login (incl. biometric prompt), simulate, poll, get alpha, submit, data fields. Retries on 429. |
| `brain/fake.py` | Offline client for `--dry-run` and tests |
| `brain/store.py` | SQLite store, one row per (expression, settings) |
| `brain/templates.py` | Template expansion, pass/fail filter, fix hints |
| `settings.toml` | Simulation settings and report thresholds |
| `alphas/starter.txt` | Hand-written starter ideas |
| `alphas/templates.txt` | Templates with `{field}` and `{window}` |

## Tuning rules used by the hints

| Result | What to change |
|---|---|
| Sharpe < 0 | Flip the sign |
| Sharpe < 0.5 | Change the idea; settings will not help |
| Turnover > 70% | Higher decay, `ts_mean` smoothing, `trade_when` |
| Sharpe ok, fitness < 1 | Lower turnover, try another neutralization |
| Fails concentration | Lower truncation, wrap in `rank()` |
| Fails self-correlation | Use a different dataset, not a small variation |

## Notes

- Thresholds in `settings.toml` are typical Delay-1 values (Sharpe 1.25, fitness 1.0, turnover 1% to 70%). The checks BRAIN returns for each alpha are the real limits, and the filter also rejects any check marked FAIL.
- A high in-sample Sharpe after many parameter tweaks is usually overfitting. Keep the number of variants per idea small.
- Read BRAIN's terms on API use and simulation limits before running large sweeps.
- Never commit `.env`.
