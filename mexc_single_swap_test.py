# Быстрый тест MEXC SWAP лимитного ордера через CCXT, с авто-подстройкой хоста.
# Запуск:
#   MEXC_KEY=... MEXC_SECRET=... python mexc_single_swap_test.py
# Параметры можно задать env:
#   SYMBOL=BAGWORK/USDT:USDT   LEVERAGE=20   NOTIONAL=6.0   HOST=contract.mexc.com

import os, time
import ccxt
from ccxt.base.errors import InvalidNonce, RequestTimeout

API_KEY    = os.getenv("MEXC_KEY", "")
API_SECRET = os.getenv("MEXC_SECRET", "")

SYMBOL     = os.getenv("SYMBOL", "BAGWORK/USDT:USDT")  # USDT-perp
LEVERAGE   = int(os.getenv("LEVERAGE", "20"))
NOTIONAL   = float(os.getenv("NOTIONAL", "6.0"))
RECV_WIN   = int(os.getenv("RECV_WIN", "60000"))
WAIT_SEC   = float(os.getenv("WAIT_SEC", "4.0"))
POST_ONLY  = os.getenv("POST_ONLY", "true").lower() == "true"

# хосты для контрактов (на некоторых провайдерах .me/.io помогают)
HOSTS = [
    os.getenv("HOST", "contract.mexc.com"),
    "contract.mexc.me",
    "contract.mexc.io",
]

def make_ex(host):
    ex = ccxt.mexc({
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "enableRateLimit": True,
        "timeout": 15000,
        "options": {
            "defaultType": "swap",
            "adjustForTimeDifference": True,
        },
    })
    # переопределим контрактный эндпоинт
    if hasattr(ex, "urls") and "api" in ex.urls:
        if isinstance(ex.urls["api"], dict):
            ex.urls["api"]["contract"] = f"https://{host}"
    return ex

def try_host(host):
    print(f"\n=== HOST: https://{host} ===")
    ex = make_ex(host)
    try:
        print("load_markets() ...")
        ex.load_markets()
        try:
            diff = ex.load_time_difference()
            print(f"time diff adjusted: {diff} ms")
        except Exception as e:
            print("time diff warn:", e)

        if SYMBOL not in ex.markets:
            # мягкий поиск
            base = SYMBOL.split("/")[0]
            cands = [s for s,m in ex.markets.items() if m.get("type") in ("swap","future") and s.startswith(base + "/")]
            raise Exception(f"маркет {SYMBOL} не найден. Похожие: {cands[:10]}")

        mkt = ex.market(SYMBOL)
        if not (mkt.get("type") == "swap" or mkt.get("contract")):
            raise Exception(f"{SYMBOL} найден, но не swap (type={mkt.get('type')})")

        print("fetch_balance(swap) ...")
        bal = ex.fetch_balance(params={"type":"swap","recvWindow":RECV_WIN})
        print("swap USDT total =", bal.get("total",{}).get("USDT"))

        # режим и плечо (one-way, cross leverage)
        try:
            ex.set_position_mode(False, SYMBOL, params={"recvWindow": RECV_WIN})
            print("position_mode = one-way")
        except Exception as e:
            print("set_position_mode warn:", e)

        try:
            # согласно MEXC swap API в ccxt: openType=2 (cross), positionType оставим по умолчанию
            ex.set_leverage(LEVERAGE, SYMBOL, params={"openType": 2, "recvWindow": RECV_WIN})
            print(f"leverage set: {LEVERAGE}x CROSS")
        except Exception as e:
            print("set_leverage warn:", e)

        ob = ex.fetch_order_book(SYMBOL, limit=5)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        if not bids or not asks:
            raise Exception("пустой стакан")
        bid = float(bids[0][0]); ask = float(asks[0][0])
        mid = (bid+ask)/2

        # расчёт шага цены + количества
        tick_digits = (mkt.get("precision", {}) or {}).get("price")
        if tick_digits is None:
            tick = max((ask-bid)/10.0, 1e-6)
        else:
            tick = 10 ** (-(tick_digits or 0))

        qty = NOTIONAL / max(mid, 1e-12)
        qty = float(ex.amount_to_precision(SYMBOL, qty))
        # уважаем минимум amount
        min_amt = ((mkt.get("limits", {}) or {}).get("amount", {}) or {}).get("min") or 0
        if min_amt and qty < min_amt:
            qty = float(ex.amount_to_precision(SYMBOL, min_amt))

        # цена: безопасно ниже bid, но положительная
        price = max(bid - 10*tick, tick)
        price = float(ex.price_to_precision(SYMBOL, price))

        print(f"TRY BUY (create_order) -> {SYMBOL} qty={qty} price={price} mid≈{mid:.10f} tick≈{tick:.10f} postOnly={POST_ONLY}")

        params = {"recvWindow": RECV_WIN, "postOnly": POST_ONLY}
        try:
            od = ex.create_order(SYMBOL, "limit", "buy", qty, price, params=params)
        except RequestTimeout as e:
            print("create_order timeout → retrying without postOnly ...")
            params["postOnly"] = False
            od = ex.create_order(SYMBOL, "limit", "buy", qty, price, params=params)

        oid = od.get("id")
        print("placed id=", oid)

        t0=time.time()
        while time.time()-t0 < WAIT_SEC:
            od = ex.fetch_order(oid, SYMBOL)
            print("status:", od.get("status"), "filled:", od.get("filled"))
            if od.get("status") in ("closed","canceled"):
                break
            time.sleep(0.8)

        try:
            ex.cancel_order(oid, SYMBOL, params={"recvWindow": RECV_WIN})
            print("cancel sent")
        except Exception as e:
            print("cancel warn:", e)

        print("✓ submit/cancel прошли на этом хосте.")
        return True

    except InvalidNonce as e:
        print("InvalidNonce:", e)
        try:
            ex.load_time_difference(); print("time re-sync done")
        except Exception:
            pass
        return False
    except Exception as e:
        print("✗ FAIL на хосте:", repr(e))
        return False
    finally:
        try:
            ex.close()
        except Exception:
            pass

def main():
    if not API_KEY or not API_SECRET:
        raise SystemExit("Нет MEXC_KEY/MEXC_SECRET в окружении.")

    any_ok = False
    for host in HOSTS:
        ok = try_host(host)
        any_ok = any_ok or ok

    if not any_ok:
        print("\nИтог: ни один хост не принял POST/submit. Это почти наверняка сетевой блок (DPI/SSL-инспекция/фаервол/антивирус/провайдер).")
        print("Проверь через net_probe.py — если POST там тоже зависает, значит дело точно в сети.")

if __name__ == "__main__":
    main()
