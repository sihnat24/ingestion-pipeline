import requests
import time
from dotenv import load_dotenv
import os
from pathlib import Path
from  datetime import datetime, timezone

import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

import asyncio
import json
import websockets


"""
--------
SUMMARY
--------

Helper methods for interacting with the Kalshi API.

Includes:
- Authentication helpers (key loading, RSA-PSS signing, header generation)
- Active market lookup by series ticker
- Market snapshot retrieval and normalization
- Orderbook retrieval

Helpful links:
Kalshi exchange status: https://docs.kalshi.com/api-reference/exchange/get-exchange-status
Kalshi trade API: https://docs.kalshi.com/api-reference/trade-api
"""

#======================================================================================================================#
#                                            IMPORTANT PARAMATERS                                                      #
#======================================================================================================================#


#API URLs - come back and clean this up, everything is functional for now
BASE_URL = "https://api.elections.kalshi.com"
PUBLIC_MARKETS_URL = f"{BASE_URL}/trade-api/v2/markets"
WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"

#======================================================================================================================#
#                                               CONFIG HELPERS                                                         #
#======================================================================================================================#

def load_kalshi_vars():
    """
    Load Kalshi API configuration from environment variables and initialize private key.

    Returns:
        tuple: (kalshi_id, kalshi_key) where kalshi_id is the API key ID string
               and kalshi_key is the loaded RSA private key object

    Raises:
        KeyError: if any required environment variable is not set
        FileNotFoundError: if the PEM file cannot be found at the specified path
    """
    kalshi_id = os.environ["KALSHI_KEY_ID"]
    key_path = os.environ["KALSHI_PEM_PATH"]
    kalshi_key = load_private_key_from_file(key_path)
    return kalshi_id, kalshi_key


def load_private_key_from_file(file_path):
    """
    load a private cryptographic key from disk into a usable Python object

    Args:
        file_path (string): path to kalshi pem private key

    Returns:
        private_key (private key object ) 
    """
    
    with open(file_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend()
        )
    return private_key


def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
    """
    sign text using RSA-PSS padding and return base64-encoded signature

    Args:
        private_key (rsa.RSAPrivateKey): RSA private key used to sign the message
        text (string): message to sign

    Returns:
        signature (string) 
    """
    message = text.encode('utf-8')
    try:
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode('utf-8')
    except InvalidSignature as e:
        raise ValueError("RSA sign PSS failed") from e
    


def header_generation(method, path, body, kalshi_id, kalshi_key):
    """
    generate authenticated headers for Kalshi API requests using RSA-PSS signature

    Args:
        method (string): HTTP method for the request
        path (string): API path used for signing and request URL construction
        body (string): request body to include in signature for non-GET requests
        kalshi_id (string): Kalshi API key ID used to identify the client
        kalshi_key (object): loaded RSA private key used to sign the request

    Returns:
        headers (dict) 
    """
    timestamp = str(int(time.time() * 1000))

    path_to_sign = path.split("?")[0]
    body_to_sign = body if method != "GET" else ""

    message = f"{timestamp}{method}{path_to_sign}{body_to_sign}"
    signature = sign_pss_text(kalshi_key, message)

    headers= {
        "KALSHI-ACCESS-KEY": kalshi_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json",
    }

    return headers


#======================================================================================================================#
#                                           API DATA GATHERING                                                         #
#======================================================================================================================#

def get_all_markets(series_ticker, limit=100):
    """ Given series ticker, return last 100 markets


        see https://docs.kalshi.com/api-reference/market/get-market#get-market for all parameters in dict
    
        returns: dict of last 'limit' markets
    """
    params = {
        "limit" : limit,
        "series_ticker" : series_ticker
    }
    resp = requests.get(PUBLIC_MARKETS_URL, params=params)
    resp.raise_for_status()
    markets = resp.json()["markets"]
    
    return markets


def get_active_market(series_ticker, limit=1000, just_tick=True):
    """ Given series ticker, print out details of active market and return the market dict"""
    params = {
        "limit" : limit,
        "series_ticker" : series_ticker
    }
    resp = requests.get(PUBLIC_MARKETS_URL, params=params)
    resp.raise_for_status()
    markets = resp.json()["markets"]
    for m in markets:
        if m.get('status') == 'active':
            print(f"ACTIVE MARKET | {m.get("title")} | close time: {m.get("close_time")} | {m.get("status")}")
            return m.get("ticker") if just_tick else m
    
    print("No active markets were found for this series ticker :(")
    return


def get_next_market(series_ticker, limit=100, just_tick = True):

    params = {
        'limit': limit,
        'series_ticker': series_ticker 
    }
    
    #get dict of all recent markets
    resp = requests.get(PUBLIC_MARKETS_URL, params)
    resp.raise_for_status()
    markets = resp.json()["markets"]
    markets.sort(key=lambda m: m['open_time']) #sort by open time

    #get current time, return ticker of first market with openeing AFTER current time
    now = datetime.now(timezone.utc)

    for m in markets:
        if m.get('status') == 'initialized' and now < datetime.fromisoformat(m.get("open_time")):
            print(f"NEXT MARKET | {m.get("title")} | open time: {m.get("open_time")} | {m.get("status")}")
            return m.get("ticker") if just_tick else m
    
    print("Next market could not be found. Returning NONE")
    return None


#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!#

def get_market_snapshot(market_ticker):
    """
    Given a market ticker, return its information.
    Returns: the data in dictionary format
    """
    url = f"{PUBLIC_MARKETS_URL}/{market_ticker}"
    data = requests.get(url)
    data.raise_for_status()
    return data.json()

#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!#

def extract_market_data(snapshot):

    """
    extract normalized fields from a market snapshot for downstream use

    Args:
        snapshot (dict): raw market snapshot returned by the API

    Returns:
        market_data (dict) 
    """
    
    m = snapshot["market"]
    return {
            # Receipt timestamp (ground truth for joins)
            "ts": datetime.now(timezone.utc),

            # Identifiers
            "market_ticker": m["ticker"],
            "event_ticker": m["event_ticker"],
            "title": m["title"],
            "status": m["status"],

            # Pricing (¢)
            "yes_bid": m["yes_bid_dollars"],
            "yes_ask": m["yes_ask_dollars"],
            "no_bid": m["no_bid_dollars"],
            "no_ask": m["no_ask_dollars"],
            "last_price": m["last_price_dollars"],

            # Liquidity / participation
            "volume": m["volume_fp"],
            "volume_24h": m["volume_24h_fp"],
            "open_interest": m["open_interest_fp"],
            "liquidity": m["liquidity_dollars"],

            # Contract mechanics
            "floor_strike": m["floor_strike"],
            "strike_type": m["strike_type"],
            "tick_size": m["tick_size"],

            # Timing / settlement
            "close_time": m["close_time"],
            "expected_expiration_time": m["latest_expiration_time"],
            "expiration_time": m["expiration_time"],
            "settlement_timer_seconds": m["settlement_timer_seconds"],

            # Full payload for safety
            "raw_json": snapshot
        }



def get_market_result(market_ticker):
    """
    extract result of market after it closes 

    Args:
        market_ticker (str): market primary key

    Returns:
        market_data (str), yes or no
    """



    #market[status] has multiple values
    # initialized : future markets, its been loaded but is not active yet
    # active: current market being used
    # finalized: market is finished running 

    url = f"{PUBLIC_MARKETS_URL}/{market_ticker}"
    data = requests.get(url)
    data.raise_for_status()

    
    m = data.json()["market"]
    return (market_ticker, m.get('result'))


def get_orderbook_snapshot(
    market_ticker: str, 
    kalshi_id: str,
    kalshi_key):
    """
    given a market ticker, return the market's LIMIT orderbook

    Args:
        ticker (string): Kalshi market ticker to query

    Returns:
        orderbook (dict) 
    """
    path = f"/trade-api/v2/markets/{market_ticker}/orderbook"
    header = header_generation("GET",
                               path,
                               "",
                                kalshi_id,
                                kalshi_key)
    
    url = BASE_URL + path
    response = requests.get(url, headers=header)
    response.raise_for_status()
    response = response.json()
    ob = response['orderbook_fp']
    return {'yes': ob.get('yes_dollars'), 'no': ob.get('no_dollars')}


#======================================================================================================================#
#                                           WEB SOCKET INGESTION.                                                      #
#======================================================================================================================#

async def websocket_ingest(
    market_ticker: str,
    series_ticker: str,
    kalshi_id: str,
    kalshi_key,
    out_queue: asyncio.Queue | None = None
):
    """
    Connect to Kalshi WebSocket and ingest live market updates.

    Args:
        market_ticker (str): active market ticker (e.g. BTC-24FEB15-15M)
        series_ticker (str): series ticker for context / validation
        out_queue (asyncio.Queue, optional): queue to emit parsed messages into
    """

    subscribe_msg = {
    "id": 1,
    "cmd": "subscribe",
    "params": {
        "channels": ["orderbook_delta"],
        "market_ticker": market_ticker 
        }
    }


    try:
        async with websockets.connect(WS_URL,
                                        additional_headers= header_generation(
                                        "GET",
                                        "/trade-api/ws/v2",
                                        "",
                                        kalshi_id,
                                        kalshi_key),
                                        ping_interval=20) as ws:
            
            #async with: opens resources, guarantees cleanup on exit, works with await
            #websockets.connect(): initiates TCP+WS handshake, returns live socket object
            #ping_interval=20:sends heartbeat every 20s, prevents idle timeouts 
            print(f"[WS] Connected to Kalshi for {market_ticker}")

            await ws.send(json.dumps(subscribe_msg)) 
            #await: puases until msg is sent, does not block other tasks
            #json.dumps: websocket send strings, not python dicts

            while True:
                try:
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=3) #waits here, this is where other async functions can fire in meantime
                except asyncio.TimeoutError:
                    # 3s of silence—check if market changed
                    active_tick = get_active_market(series_ticker)
                    if active_tick != market_ticker:
                        if out_queue is not None:
                            await out_queue.put(None)

                        print(f"Market ended: {market_ticker} → {active_tick}")
                        break
                    continue  # market still active, keep listening

                msg = json.loads(raw_msg)

                event = {
                    "ts": datetime.now(timezone.utc),
                    "source": "kalshi_ws",
                    "market_ticker": market_ticker,
                    "series_ticker": series_ticker,
                    "payload": msg
                }

                if out_queue is not None:
                    await out_queue.put(event)
                else:
                    print(event)

    except websockets.exceptions.ConnectionClosed as e:
        print(f"[WS] Connection closed ({e})")
        return

    except Exception as e:
        print(f"[WS] Unexpected error: {e}")
        return


    

#======================================================================================================================#
#                                           API ACCOUNT INTERACTION                                                    #
#======================================================================================================================#

#here i want to put methods that actually interact with the account aka buying/selling contracts
#also checking prices, potentially adding some safeguards for bot interaction


