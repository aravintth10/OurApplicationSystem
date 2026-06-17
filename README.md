# Smart Candidate Ranking System

> Intelligent resume ranking that finds real talent, not keyword stuffers.

**Team:** Brain Cells and Caffeine

## What It Does

Ranks 100,000+ candidate profiles for a Senior ML Engineer role using multi-signal scoring — filtering out honeypots, keyword stuffers, and inflated profiles to surface genuinely qualified candidates.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the ranking pipeline
python rank.py --candidates ./candidates.jsonl --out ./submission.csv
```

## Project Structure

| File | Purpose |
|---|---|
| `rank.py` | Entry point — CLI interface, orchestrates the pipeline |
| `scorer.py` | Core scoring engine (5 weighted components) |
| `skills_config.py` | Centralized skill definitions & thresholds |
| `honeypot_detector.py` | Pre-filter for trap/fake candidates |
| `app.py` | Streamlit sandbox for live demo |
| `validate_submission.py` | Validates output CSV format |

## How It Works

1. **Load** — Reads candidate profiles from JSONL
2. **Filter** — Honeypot detector removes ~28% fake/trap candidates
3. **Score** — Multi-signal engine evaluates career trajectory (50%), skill relevance (20%), experience (15%), education (10%), and location (5%)
4. **Rank & Export** — Top 100 candidates written to `submission.csv`

## Results

- **100K candidates** scored in ~60 seconds on CPU
- **27,987 honeypots** detected and filtered
- **0% honeypot rate** in Top 100
- No GPU or external APIs required

## Tech Stack

- Python 3.10
- Pandas
- Streamlit
- python-dotenv

## Live Demo

🔗 [ourapplicationsystem.streamlit.app](https://ourapplicationsystem.streamlit.app/)

## License

MIT
