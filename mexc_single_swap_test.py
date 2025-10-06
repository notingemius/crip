# mexc_single_swap_test_fallback.py
# Тест размещения лимита на MEXC USDT-perp с перебором хостов contract.*
# pip install ccxt requests urllib3

import time, socket, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import ccxt
from ccxt.base.errors import InvalidNonce

API_KEY    = "mx0vglwadOhTZvqD9J"
API_SECRET = "6ae5201403f14f89aa571438f9c49593"

SYMBOL_UI  = "BAGWORK_USDT"  # можно: BAGWORK/USDT, BAGWORK/USDT:USDT, BAGWORK_USDT
LEVERAGE   = 20
NOTIONAL   = 6.0
RECV_WIN   = 60000
WAIT_SEC   = 4.0
POST_ONLY  = True

CONTRACT_HOSTS = [
    "https://contract.mexc.com",
    "https://contract.mexc.me",
    "https://contract.mexc.io",
]

def ui_to_ccxt(sym_ui: str) -> str:
    s = sym_ui.strip().upper().replace(" ", "")
    if s.endswith(":USDT"):
        if "/USDT:USDT" in s: return s
        return f"{s[:-6]}/USDT:USDT"
    if s.endswith("_USDT"):
        return f"{s[:-6]}/USDT:USDT"
    if s.endswith("/USDT"):
        return f"{s[:-5]}/USDT:USDT"
    return f"{s}/USDT:USDT"

def make_session():
    sess = requests.Session()
    # не использовать системные прокси/переменные окружения
    sess.trust_env = False
    # ретраи на 429/5xx
    retry = Retry(total=2, backoff_factor=0.4, status_forcelist=[429,500,502,503,504], allowed_methods=["GET","POST"])
    sess.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=100))
    return sess

def build_exchange(base_url: str):
    sess = make_session()
    ex = ccxt.mexc({
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "enableRateLimit": True,
        "timeout": 30000,   # побольше
        "session": sess,    # используем нашу сессию с ретраями и без прокси
        "options": {
            "defaultType": "swap",
            "adjustForTimeDifference": True,
        },
    })
    # подменяем контрактный эндпоинт на нужный хост
    ex.urls["api"]["contract"] = base_url
    return ex

def try_submit_on_host(host_base: str):
    print(f"\n=== HOST: {host_base} ===")
    ex = build_exchange(host_base)
    symbol = ui_to_ccxt(SYMBOL_UI)

    try:
        print("load_markets() ...")
        ex.load_markets()
        diff = ex.load_time_difference()
        print(f"time diff adjusted: {diff} ms")

        if symbol not in ex.markets:
            base = symbol.split("/")[0]
            cands = [s for s,m in ex.markets.items() if (m.get('type') in ('swap','future')) and s.startswith(base + "/")]
            raise Exception(f"В маркете нет {symbol}. Похожие: {cands[:10]}")

        mkt = ex.market(symbol)
        if not (mkt.get("type") == "swap" or mkt.get("contract")):
            raise Exception(f"{symbol} найден, но это не swap-маркет (type={mkt.get('type')}).")

        bal = ex.fetch_balance(params={"type":"swap","recvWindow": RECV_WIN})
        print("swap USDT total =", bal.get("total",{}).get("USDT"))

        # режим и плечо
        try:
            ex.set_position_mode(False, symbol, params={"recvWindow": RECV_WIN})  # one-way
            print("position_mode = one-way")
        except Exception as e:
            print("set_position_mode warn:", e)
        try:
            ex.set_leverage(LEVERAGE, symbol, params={"marginMode":"cross","openType":2,"positionType":1,"recvWindow":RECV_WIN})
            print(f"leverage set: {LEVERAGE}x CROSS")
        except Exception as e:
            print("set_leverage warn:", e)

        ob = ex.fetch_order_book(symbol, limit=5)
        bids = ob.get("bids") or []; asks = ob.get("asks") or []
        if not bids or not asks:
            raise Exception("Пустой стакан")
        bid = float(bids[0][0]); ask = float(asks[0][0])
        mid = (bid + ask)/2.0

        prec = (mkt.get("precision",{}) or {}).get("price", 0) or 0
        tick = 10 ** (-prec) if isinstance(prec,int) else max((ask-bid)/10.0, 1e-6)

        qty_raw = NOTIONAL / max(mid, 1e-12)
        qty = float(ex.amount_to_precision(symbol, qty_raw))
        min_amt = (((mkt.get("limits",{}) or {}).get("amount",{}) or {}).get("min") or 0)
        if min_amt and qty < min_amt:
            qty = float(ex.amount_to_precision(symbol, min_amt))

        # цена заведомо ниже — чтобы ордер точно остался в книге (и прошёл как лимит)
        price = float(ex.price_to_precision(symbol, bid - 8*tick))
        print(f"TRY BUY -> {symbol} qty={qty} price={price} mid≈{mid:.10f} tick≈{tick}")

        params = {"recvWindow": RECV_WIN, "postOnly": POST_ONLY}
        try:
            od = ex.create_order(symbol, "limit", "buy", qty, price, params=params)
            oid = od.get("id")
            print("placed id=", oid)
        except Exception as e:
            print("create_order error:", repr(e))
            # как в твоих тестах — попробуем без postOnly
            if POST_ONLY:
                print("retry without postOnly ...")
                od = ex.create_order(symbol, "limit", "buy", qty, price, params={"recvWindow":RECV_WIN, "postOnly": False})
                oid = od.get("id")
                print("placed id=", oid)

        t0 = time.time()
        while time.time() - t0 < WAIT_SEC:
            od = ex.fetch_order(oid, symbol)
            print("status:", od.get("status"), "filled:", od.get("filled"))
            if od.get("status") in ("closed", "canceled"):
                break
            time.sleep(0.7)

        try:
            ex.cancel_order(oid, symbol, params={"recvWindow": RECV_WIN})
            print("cancel sent")
        except Exception as e:
            print("cancel warn:", e)

        print(f"✓ УСПЕХ на хосте {host_base} — размещение/отмена прошли до API.")
        return True

    except InvalidNonce as e:
        print("InvalidNonce:", e)
        try:
            ex.load_time_difference(); print("time re-sync done")
        except Exception:
            pass
        return False
    except Exception as e:
        print("✗ FAIL на хосте", host_base, "::", repr(e))
        return False
    finally:
        try: ex.close()
        except Exception: pass

def main():
    ok = False
    for host in CONTRACT_HOSTS:
        if try_submit_on_host(host):
            ok = True
            break
    if not ok:
        print("\nИтог: ни один хост не принял POST. Это почти наверняка блок на стороне сети/ПО. Попробуй VPN/другую сеть или отключи SSL-инспекцию.")

if __name__ == "__main__":
    main()
