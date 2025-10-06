import os, time
import ccxt
from ccxt.base.errors import InvalidNonce

KEY = os.getenv("MEXC_KEY", "")
SEC = os.getenv("MEXC_SECRET", "")
SYMBOL = os.getenv("SYMBOL", "BAGWORK/USDT:USDT")  # можно переопределять в Render

def mexc_swap():
    return ccxt.mexc({
        "apiKey": KEY, "secret": SEC,
        "enableRateLimit": True, "timeout": 20000,
        "options": {"defaultType": "swap", "adjustForTimeDifference": True},
    })

def main():
    if not KEY or not SEC:
        raise SystemExit("Нет MEXC_KEY/MEXC_SECRET")

    ex = mexc_swap()
    print("load_markets() ..."); ex.load_markets()
    try:
        diff = ex.load_time_difference()
        print("time diff:", diff, "ms")
    except Exception as e:
        print("time diff warn:", e)

    if SYMBOL not in ex.markets:
        raise SystemExit(f"Маркет не найден: {SYMBOL}")

    print("fetch_balance(swap) ...")
    bal = ex.fetch_balance(params={"type":"swap","recvWindow":60000})
    print("USDT swap total:", bal.get("total",{}).get("USDT"))

    # Просто проверяем доступность POST через приватный эндпоинт без реальной сделки:
    # fetch_open_orders использует приватный POST/GET у фьючерсов
    try:
        oo = ex.fetch_open_orders(SYMBOL, params={"recvWindow":60000})
        print("open orders:", len(oo))
    except InvalidNonce as e:
        print("InvalidNonce:", e)
    except Exception as e:
        print("Private POST error:", repr(e))

    ex.close()

if __name__ == "__main__":
    main()
