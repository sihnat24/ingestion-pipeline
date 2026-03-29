# Prediction Market Data Ingestion

A real-time data collection pipeline that streams order flow from Kalshi's prediction markets and aggregates spot price data from CoinGecko, persisting everything to a local time-series stack for analysis.

## Architecture

Three concurrent async tasks run continuously:

- **`market_cycle`** — connects to Kalshi via WebSocket and receives live orderbook deltas for the active BTC 15-minute contract. When a contract expires, it automatically rolls to the next active market and reconnects. Orderbook events are pushed onto an `asyncio.Queue` and drained by a `write_worker`, decoupling ingestion latency from write latency.
- **`ingest_coin_data`** — polls CoinGecko every 60 seconds for BTC spot price, 24h metrics, market cap, and supply data.
- **`heartbeat`** — writes a liveness signal to InfluxDB every 60 seconds.

All data lands in **InfluxDB 2**, with a **Grafana** dashboard for live monitoring.

```
Kalshi WebSocket  (orderbook deltas)  ─┐
Kalshi REST       (market snapshots)   ├──► asyncio.Queue ──► write_worker ──► InfluxDB
CoinGecko REST    (spot price, 60s)   ─┘
CF Benchmarks RTI (settlement price)  ──────────────────────────────────────► InfluxDB

InfluxDB ──► Grafana (live dashboard, :3000)
         └──► btc_terminal_plots.py (terminal analysis)
```

### InfluxDB Measurements

| Measurement | Source | Contents |
|---|---|---|
| `market_snapshot` | Kalshi REST | Bid/ask, last price, open interest, volume |
| `orderbook` | Kalshi WebSocket | Full limit order book by price level |
| `orderbook_delta` | Kalshi WebSocket | Incremental updates with sequence numbers |
| `coingecko_snapshot` | CoinGecko REST | Spot price, 24h change, market cap |
| `rti_snapshot` | CF Benchmarks | Settlement price + OHLC candlesticks (1M, 15M, 1H, 6H) |
| `heartbeat` | Internal | Liveness signal |

Sequence numbers and write timestamps are stored on each orderbook delta, enabling measurement of end-to-end event latency.

### Price Sources

Three price sources are captured for BTC:

1. **Kalshi mid-price** — the prediction market's implied probability converted to a price
2. **CoinGecko spot** — aggregated spot price across exchanges
3. **CF Benchmarks RTI** — the authoritative settlement price Kalshi uses for contract resolution

## Stack

- **Python 3.12** with `asyncio` for concurrent ingestion
- **InfluxDB 2** — time-series storage
- **Grafana** — live monitoring dashboard
- **Docker Compose** — orchestrates all three services

## Setup

**1. Configure environment variables**

Copy the example below into a `.env` file at the repo root:

```
KALSHI_KEY_ID=your-kalshi-key-id
KALSHI_PEM_PATH=/secrets/kalshi.pem
INFLUX_URL=http://influxdb:8086
INFLUX_USERNAME=admin
INFLUX_PASSWORD=your-password
INFLUX_ORG=kalshi
INFLUX_BUCKET=markets
INFLUX_TOKEN=your-token
SECRETS_PATH=/path/to/local/secrets/dir
```

The `SECRETS_PATH` directory should contain your `kalshi.pem` private key file. It is mounted into the bot container at `/secrets`.

**2. Start the stack**

```bash
docker-compose up
```

This starts InfluxDB (`:8086`), Grafana (`:3000`), and the bot. The bot waits 5 seconds for InfluxDB to initialize before connecting.

**3. Run locally (without Docker)**

```bash
pip install -r requirements.txt
cd state
python ingest_15m_btc.py
```

Requires a running InfluxDB instance and `INFLUX_URL` pointing to it.

## Analysis

`state/btc_terminal_plots.py` reads aggregated series from InfluxDB and plots Kalshi prediction market price vs. CoinGecko spot price directly in the terminal.

```bash
cd state
python btc_terminal_plots.py
```

To wipe all data from the InfluxDB bucket:

```bash
python state/wipe.py
```
