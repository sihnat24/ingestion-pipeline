import asyncio
from dotenv import load_dotenv


#custom modules
import kalshi_helpers as kh
import influx_helpers as ih
import coingecko_helpers as cg
import config


#config and environment variables
BTC_15M_SER = config.BTC_15M_SER
CG_BTC_ID = config.CG_BTC_ID
load_dotenv()


async def market_cycle(
        series_tick, 
        kalshi_id, 
        kalshi_key,
        ifx_api,
        ifx_bucket,
        ifx_org):
    
    while True:
        #get snapshots
        active_tick = kh.get_active_market(series_tick)

        #instantiate current queue
        curr_queue = asyncio.Queue()

        #log overall market snapshot
        market_snap = kh.get_market_snapshot(active_tick)
        ih.wrt_kalshi_market_snapshot(ifx_api, ifx_bucket, ifx_org, snapshot=market_snap)

        #listen to websocket until it ends. ingest injects a none into the queue when market switch is detected
        await asyncio.gather(
            kh.websocket_ingest(active_tick, BTC_15M_SER, kalshi_id, kalshi_key, curr_queue), #adds messages to the queue
            write_worker(curr_queue, active_tick, ifx_api, ifx_bucket, ifx_org),
        )


async def write_worker(queue, market_tick, write_api, bucket, org):

    while True:
        message = await queue.get()

        if message is None:  # Sentinel value = stop signal
            break
        
        msg_type = message["payload"]["type"]
        
        
        if msg_type == "orderbook_snapshot":
            ih.wrt_kalshi_orderbook(write_api, bucket, org, market_tick, message=message)
        elif msg_type == "orderbook_delta":
            ih.write_ws_orderbook_delta(write_api, bucket, org, message=message)

        queue.task_done()
        

async def ingest_coin_data(
        coin_id,
        ifx_api,
        ifx_bucket,
        ifx_org):

        while True: 
            coin_snap = cg.get_coin_snapshot(coin_id)
            ih.write_coingecko_snapshot(ifx_api, ifx_bucket, ifx_org,data=coin_snap)

            await asyncio.sleep(2 * 60) #basic 2 minute ingestion for now 


async def heartbeat(ifx_api, ifx_bucket, ifx_org):
    while True:
        ih.write_heartbeat(ifx_api, ifx_bucket, ifx_org)
        await asyncio.sleep(60)




async def main():
    #load variables
    _, _, bucket, token, org = ih.load_influx_vars()
    kalshi_id, kalshi_key = kh.load_kalshi_vars()

    #setup influx client
    influx_client = ih.get_influx_client("http://localhost:8086", token, org)
    write_api = ih.get_write_api(influx_client)



    await asyncio.gather(
        market_cycle(BTC_15M_SER, kalshi_id, kalshi_key, write_api, bucket, org),
        ingest_coin_data(CG_BTC_ID, write_api, bucket, org),
        heartbeat(write_api, bucket, org)
    )



if __name__ == "__main__":
    asyncio.run(main())
