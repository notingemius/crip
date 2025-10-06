import socket, ssl, time, requests

HOST = "contract.mexc.com"
PORT = 443
GET_URL = f"https://{HOST}/"
POST_URL = f"https://{HOST}/api/v1/private/order/submit"

def dns_check(host):
    t0=time.time()
    infos = socket.getaddrinfo(host, PORT, proto=socket.IPPROTO_TCP)
    dt = int((time.time()-t0)*1000)
    return True, dt, infos

def tls_check(host):
    t0=time.time()
    ctx = ssl.create_default_context()
    with socket.create_connection((host, PORT), timeout=5) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            ssock.do_handshake()
    dt = int((time.time()-t0)*1000)
    return True, dt

def http_get(url):
    t0=time.time()
    r = requests.get(url, timeout=8)
    dt = int((time.time()-t0)*1000)
    return r.status_code, dt, len(r.content)

def http_post(url):
    # спецом без подписи; если сеть норм — придёт 4xx быстро.
    t0=time.time()
    try:
        r = requests.post(url, timeout=8, json={"dummy": True})
        dt = int((time.time()-t0)*1000)
        return True, r.status_code, dt, r.text[:200]
    except Exception as e:
        return False, None, None, repr(e)

def main():
    ok, dt, infos = dns_check(HOST)
    print(f"-- DNS --\nOK ({dt} ms) :: {infos[:2]}\n")

    ok, dt = tls_check(HOST)
    print(f"-- TLS --\nOK ({dt} ms) :: handshake OK\n")

    code, dt, ln = http_get(GET_URL)
    print(f"-- HTTP GET --\n{code} in {dt} ms :: len={ln}\n")

    ok, code, dt, body = http_post(POST_URL)
    if ok:
        print(f"-- HTTP POST --\nOK {code} in {dt} ms :: body[:200]={body!r}\n")
    else:
        print(f"-- HTTP POST --\nFAIL :: {body}\n")

    if not ok:
        print("Вывод: POST у тебя не проходит. Это почти всегда DPI/антивирус/фаервол или провайдер.")
    else:
        print("Вывод: POST доступен. Значит дальше можно тестировать CCXT ордера.")

if __name__ == "__main__":
    main()
