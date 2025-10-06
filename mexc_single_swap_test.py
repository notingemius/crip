import time
import requests

HOSTS = [
    "contract.mexc.com",
    "contract.mexc.me",
    "contract.mexc.io",
]

# 1) Контрольный POST на внешний сервис (должен всегда работать, если сеть норм)
TEST_POST_URL = "https://httpbin.org/post"

# 2) «Безопасный» POST на приватный контрактный путь MEXC:
#    ничего не подпишем → если POST доступен, сервер быстро вернёт 4xx (например 401/403/400).
#    Если POST заблокирован DPI/фаерволом, будет timeout/connection error.
MEXC_PATH = "/api/v1/private/order/submit"  # НЕ размещает ордера — просто проверяем сам POST

TIMEOUT = 8  # секунд

def try_post(url, json=None, timeout=TIMEOUT):
    t0 = time.time()
    try:
        r = requests.post(url, json=json or {"dummy": True}, timeout=timeout)
        dt = int((time.time() - t0) * 1000)
        return ("OK", r.status_code, dt, r.text[:200])
    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        return ("FAIL", None, dt, repr(e))

def main():
    # Контроль: общий POST в интернет
    print("== Control POST to httpbin ==")
    st, code, ms, body = try_post(TEST_POST_URL, json={"probe": "ok"})
    print(f"{st} :: code={code} :: {ms} ms :: {body!r}\n")

    # Проверка POST на контрактные хосты MEXC
    for host in HOSTS:
        url = f"https://{host}{MEXC_PATH}"
        print(f"== POST -> {url} ==")
        st, code, ms, body = try_post(url)
        if st == "OK":
            # 2xx/3xx/4xx — это уже признак, что POST ДОШЁЛ (сеть пропускает).
            # Типичный ответ будет 4xx (нет подписи / неверные креды) и это НОРМАЛЬНО.
            print(f"POST REACHABLE ✅  code={code}  time={ms} ms")
            print(f"preview: {body!r}\n")
        else:
            # timeout/connection error → сеть/ПО режет POST
            print(f"POST BLOCKED/FAIL ❌  time={ms} ms")
            print(f"error: {body}\n")

    print("Интерпретация:")
    print("  • Если httpbin=OK, а на всех mexc-хостах FAIL/timeout → почти наверняка DPI/антивирус/фаервол/провайдер режет POST на contract.mexc.*")
    print("  • Если на каком-то mexc-хосте code=4xx → это ХОРОШО: POST доходит (просто нет подписи). Значит сеть пропускает POST.\n")

if __name__ == "__main__":
    main()
