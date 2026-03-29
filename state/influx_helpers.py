from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import os
from datetime import datetime, timezone
import asyncio

"""
See https://docs.influxdata.com/influxdb/v2/api-guide/client-libraries/python/ for more documentation

"""


def load_influx_vars():
    """
    Load InfluxDB configuration from environment variables.

    Returns:
        tuple: (username, password, bucket, token, org)
    
    Raises:
        KeyError: if any required env variable not set 
    """
    INFLUX_USERNAME = os.environ["INFLUX_USERNAME"]
    INFLUX_PASSWORD = os.environ["INFLUX_PASSWORD"]
    INFLUX_BUCKET= os.environ["INFLUX_BUCKET"]
    INFLUX_TOKEN = os.environ["INFLUX_TOKEN"]
    INFLUX_ORG = os.environ["INFLUX_ORG"]

    return INFLUX_USERNAME, INFLUX_PASSWORD, INFLUX_BUCKET, INFLUX_TOKEN, INFLUX_ORG
    


def get_influx_client(url: str, token: str, org: str):
    """Initialize and return an InfluxDB client"""
    return InfluxDBClient(url=url, token=token, org=org)


def get_write_api(client: InfluxDBClient):
    return client.write_api(write_options=SYNCHRONOUS)


def wipe_bucket(client: InfluxDBClient, org: str, bucket: str):
    """Delete all data in a bucket"""
    delete_api = client.delete_api()
    delete_api.delete(
        start="1970-01-01T00:00:00Z",
        stop=datetime.now(timezone.utc).isoformat(),
        predicate='',
        bucket=bucket,
        org=org
    )
    print(f"Bucket '{bucket}' wiped.")


# ---------------------------------------------------------------------------
# REST API write helpers
# ---------------------------------------------------------------------------
 
def wrt_kalshi_market_snapshot(write_api, bucket: str, org: str, snapshot: dict):
    """
    Write a market snapshot to InfluxDB.

    Expects the raw snapshot dict returned from get_market_snapshot kalshi_helpers.py
    (same input as extract_market_data also in kalshi_helpers.py)
    """
    m = snapshot["market"]

    point = (
        Point("market_snapshot")
        .tag("market_ticker", m["ticker"])
        .tag("event_ticker",  m["event_ticker"])
        .tag("status",        m["status"])
        .tag("strike_type",   m["strike_type"])

        .field("yes_bid",    _to_float(m["yes_bid_dollars"]))
        .field("yes_ask",    _to_float(m["yes_ask_dollars"]))
        .field("no_bid",     _to_float(m["no_bid_dollars"]))
        .field("no_ask",     _to_float(m["no_ask_dollars"]))
        .field("last_price", _to_float(m["last_price_dollars"]))

        .field("volume",        _to_float(m["volume_fp"]))
        .field("volume_24h",    _to_float(m["volume_24h_fp"]))
        .field("open_interest", _to_float(m["open_interest_fp"]))
        .field("liquidity",     _to_float(m["liquidity_dollars"]))

        .field("floor_strike", _to_float(m["floor_strike"]))
        .field("tick_size",    _to_float(m["tick_size"]))
        .field("settlement_timer_seconds", _to_float(m["settlement_timer_seconds"]))

        .time(datetime.now(timezone.utc), WritePrecision.NS) #current time
    )

    write_api.write(bucket=bucket, org=org, record=point)

def wrt_kalshi_orderbook(write_api, bucket: str, org: str, market_ticker: str, message: dict):
    """
    Write a full orderbook snapshot to InfluxDB.
    
    Expects orderbook in the form:
        {"yes": [["0.0100", "35998.00"], ...], 
         "no":  [["0.0100", "12345.00"], ...]}
    
    Tags   : ticker, side
    Fields : price, quantity
    One point written per price level per side.
    """
    points = []

    orderbook = message["payload"]

    for side in ("yes", "no"):
        for order_pair in orderbook.get(side, []):
            price, quantity = order_pair
            p = (
                Point("orderbook")
                .tag("market_ticker", market_ticker)
                .tag("side", side)
                .field("price", _to_float(price))
                .field("quantity", _to_float(quantity))
                .time(datetime.now(timezone.utc), WritePrecision.NS)
            )
            points.append(p)

    if points:
        write_api.write(bucket=bucket, org=org, record=points)
    

def write_coingecko_snapshot(write_api, bucket: str, org: str, data: dict):
    """
    Write CoinGecko market data to InfluxDB.
    Expects the raw response from current_coin_data().
    """
    md = data["market_data"]

    point = (
        Point("coingecko_snapshot")
        .tag("coin_id", data["id"])
        .tag("symbol",  data["symbol"])

        # price
        .field("price_usd",                _to_float(md["current_price"]["usd"]))
        .field("high_24h_usd",             _to_float(md["high_24h"]["usd"]))
        .field("low_24h_usd",              _to_float(md["low_24h"]["usd"]))

        # changes
        .field("price_change_24h",         _to_float(md["price_change_24h"]))
        .field("price_change_pct_24h",     _to_float(md["price_change_percentage_24h"]))
        .field("price_change_pct_1h",      _to_float(md["price_change_percentage_1h_in_currency"]["usd"]))
        .field("price_change_pct_7d",      _to_float(md["price_change_percentage_7d"]))

        # market
        .field("market_cap_usd",           _to_float(md["market_cap"]["usd"]))
        .field("market_cap_change_pct_24h",_to_float(md["market_cap_change_percentage_24h"]))
        .field("total_volume_usd",         _to_float(md["total_volume"]["usd"]))

        # supply
        .field("circulating_supply",       _to_float(md["circulating_supply"]))
        .field("max_supply",               _to_float(md["max_supply"]))

        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )

    write_api.write(bucket=bucket, org=org, record=point)


# ---------------------------------------------------------------------------
# WEBSOCKET write helpers
# ---------------------------------------------------------------------------

def write_ws_orderbook_delta(write_api, bucket, org, message):
    msg = message["payload"]["msg"]
    point = (
        Point("orderbook_delta")
        .tag("ticker", message["market_ticker"])
        .tag("side",   msg["side"])
        .field("price",        _to_float(msg["price_dollars"]))
        .field("delta",        _to_float(msg["delta_fp"]))
        .field("seq", message["payload"]["seq"])
        .field("receipt_ts",   message["ts"].timestamp())  # local receipt time as float for latency calc
        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )
    write_api.write(bucket=bucket, org=org, record=point)

async def influx_consumer(
    queue: asyncio.Queue,
    write_api,
    bucket: str,
    org: str
):
    """Drain the WS event queue and write each event to InfluxDB."""
    while True:
        event = await queue.get()
        try:
            write_ws_orderbook_delta(write_api, bucket, org, event)
        except Exception as e:
            print(f"[INFLUX] Write failed: {e} — event: {event}")
        finally:
            queue.task_done()
 

 
# ---------------------------------------------------------------------------
# Internal type-coercion helpers
# ---------------------------------------------------------------------------
 
def _to_float(value) -> float | None:
    """Safely cast a value to float; return None if not possible."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
 
 
def _to_int(value) -> int | None:
    """Safely cast a value to int; return None if not possible."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
 

# ---------------------------------------------------------------------------
# Run assurance
# ---------------------------------------------------------------------------

def write_heartbeat(write_api, bucket, org):
    point = (
        Point("heartbeat")
        .field("alive", 1)
        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )
    write_api.write(bucket=bucket, org=org, record=point)