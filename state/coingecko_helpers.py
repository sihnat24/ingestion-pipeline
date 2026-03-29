import os
from datetime import datetime, timezone
import requests
import numpy as np
from dotenv import load_dotenv
import pandas as pd
from pycoingecko import CoinGeckoAPI

"""
Helper methods for interacting with the CoinGecko API.

Note: API key is optional — CoinGecko's public endpoints work without one,
but a pro key removes rate limits and unlocks additional endpoints.


Includes:
- Historical price retrieval (market chart)
- OHLC data via pycoingecko
- Current coin snapshot retrieval
- Normalized data extraction for downstream storage

Helpful links:
CoinGecko API docs: https://docs.coingecko.com/
CoinGecko endpoint overview: https://docs.coingecko.com/reference/endpoint-overview
pycoingecko library: https://github.com/man-c/pycoingecko
"""

# ---------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------

def load_coingecko_vars():
    """
    Load CoinGecko API configuration from environment variables.
    
    Note: API key is optional — CoinGecko's public endpoints work without one,
    but a pro key removes rate limits and unlocks additional endpoints.

    Returns:
        tuple: (api_key,) where api_key is None if COINGECKO_API_KEY is not set
    """
    api_key = os.environ.get("COINGECKO_API_KEY", None)
    return (api_key,)

#======================================================================================================================#
#                                           HISTORICAL DATA                                                            #
#======================================================================================================================#


def get_historical_prices(id,currency="usd", days=1):
    """
    get historical prices for a coin over a time window

    Args:
        id (string): coin id, eg ethereum, bitcoin, solana, xrp
        currency (string): currency for prices, eg usd
        days (int): day range from today

    Returns:
        data (dict) 
    """

    url = f"https://api.coingecko.com/api/v3/coins/{id}/market_chart"

    params = {
        "vs_currency": currency,
        "days": days
    }

    response = requests.get(url, params=params)
    data = response.json()

    return data


def high_low_range(id:str, currency:str, days:str):
    
    """
    get open, high, low, and close over the past K days for a coin

    Args:
        id (string): coin id, eg ethereum, bitcoin, solana, xrp
        currency (string): currency for prices, eg usd
        days (string): day range from today

    Returns:
        ohlc_df (pandas.DataFrame) 
    """

    gc = CoinGeckoAPI()
    ohlc = gc.get_coin_ohlc_by_id(id=id, vs_currency=currency, days=days)
    df = pd.DataFrame(ohlc)
    df.columns = ["date","open","high","low","close"]
    df.set_index("date", inplace = True)
    
    return df



def get_coin_snapshot(id, key=None):
    """
    get current coin information from CoinGecko

    Args:
        id (string): coin id, eg ethereum, bitcoin, solana, xrp
        key (string): CoinGecko pro API key for authentication

    Returns:
        data (dict) 
    """

    url = f"https://api.coingecko.com/api/v3//coins/{id}"

    headers = {"x-cg-pro-api-key": key}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    return data



def extract_coingecko_data(raw_data: dict, coin_id: str) -> dict:
    
    """
    extract normalized fields from a CoinGecko response for downstream use

    Args:
        raw_data (dict): raw CoinGecko response payload
        coin_id (string): coin id associated with the payload

    Returns:
        market_data (dict) 
    """
    
    snapshot = {
    "ts": datetime.now(timezone.utc),
    "coin_id": coin_id,
    "payload": raw_data
    }
    
    md = raw_data["market_data"]

    price = md["current_price"]["usd"]
    high_24h = md["high_24h"]["usd"]
    low_24h = md["low_24h"]["usd"]
    volume_24h = md["total_volume"]["usd"]

    range_24h = high_24h - low_24h
    normalized_range = range_24h / price if price else None
    range_per_volume = range_24h / volume_24h if volume_24h else None

    return {
        # receipt timestamp
        "ts": snapshot["ts"],

        # identity
        "coin_id": coin_id,

        # FAST MARKET CONTEXT
        "price_usd": price,
        "high_24h": high_24h,
        "low_24h": low_24h,
        "range_24h": range_24h,

        "price_change_1h_pct": md["price_change_percentage_1h_in_currency"]["usd"],
        "price_change_24h_pct": md["price_change_percentage_24h"],
        "price_change_24h_abs": md["price_change_24h"],

        "volume_24h": volume_24h,
        "last_updated": md["last_updated"],

        # SLOW CONTEXT (still stored, but not frequently polled)
        "market_cap": md["market_cap"]["usd"],
        "circulating_supply": md["circulating_supply"],
        "ath": md["ath"]["usd"],
        "atl": md["atl"]["usd"],

        # Derived (cheap + useful)
        "normalized_range": normalized_range,
        "range_per_volume": range_per_volume,

        # raw payload for safety
        "raw_json": raw_data
    }
