from state.kalshi_api import get_active_15m, get_market_snapshot
from state.config import BTC_15M_SER, ETH_15M_SER, XRP_15M_SER, SOL_15M_SER



#idea: momentum confused idea? trades feel like the swing, its usually not very up or down
#if we could identify how often these trends break over the margin, we could implement a strat taht indentifies potentiall longer slides and locks in small profits, say 5 cents

#OR WHEN HEDGING, particularly in early scenarios, potentially locking 





def bitcoin():
    #  observe market
    #     update state
    #     if market is tradeable:
    #         evaluate EV
    #         maybe trade
    #     sleep / backoff


    while True: #run constantly
        current_ticker = get_active_15m(BTC_15M_SER)
        
        while get_active_15m(BTC_15M_SER) == current_ticker:
            snapshot = get_market_snapshot(current_ticker)
