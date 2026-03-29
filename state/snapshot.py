from dataclasses import dataclass
from state.kalshi_api import get_market_snapshot, get_active_15m

from state.config import BTC_15M_SER, ETH_15M_SER, XRP_15M_SER, SOL_15M_SER

"""
This module contains class definititions for snapshots of the market which we can then use for future
decision making



"""




@dataclass
class MarketSnapshot:
    yes_bid: int
    yes_ask: int
    no_bid: int
    no_ask: int
    last_price: float
    time_to_close: float
    btc_price: float | None
    strike_price: float



    

