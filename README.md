# BESS Dashboard

Interactive Plotly dashboard combining **Amber Electric** price/grid data with **Fox ESS** inverter and battery data into a single self-contained HTML file.

## Features

- 30-day (configurable) view of grid import/export, home load, AC solar, spot price, and battery SoC
- Parquet file cache — past days are fetched once and served locally on subsequent runs
- Four colour themes: `sharp` (default), `synthwave`, `glacier`, `inferno`
- Zoomable, pannable chart with range selector and slider

## Prerequisites

- Python 3.11+
- An [Amber Electric](https://www.amber.com.au/) account with a personal access token
- A [Fox ESS Cloud](https://www.foxesscloud.com/) account with an API key

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in your tokens
```

`.env`:
```
AMBER_API_TOKEN=psk_your_token_here
FOXESS_API_KEY=your_foxess_api_key_here
```

## Usage

```bash
python main.py                  # last 30 days → output/dashboard.html
python main.py --days 7         # last 7 days
python main.py --out my.html    # custom output path
```

The dashboard opens automatically in your default browser when complete.

## Project Structure

```
main.py          Entry point
amber/
  client.py      Amber Electric API client (usage + pricing)
  chart.py       Plotly dashboard builder
foxess/
  client.py      Fox ESS Cloud API client (inverter history)
cache.py         Parquet file cache (one file per source per day)
cache/           Generated cache files (git-ignored)
output/          Generated HTML files (git-ignored)
```

## Data Sources

| Trace | Source | Unit |
|---|---|---|
| Grid Export | Amber `feedIn` channel | kW |
| Grid Import | Amber `general` channel | kW |
| Home Load | Fox ESS `loadsPower` | kW |
| Solar (AC) | Fox ESS `meterPower2` | kW |
| Spot Price | Amber `spotPerKwh` | c/kWh |
| SoC | Fox ESS `SoC` | % |
