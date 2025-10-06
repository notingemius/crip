# mexc_contract_ping.py
import socket, ssl, time, requests

HOST = "contract.mexc.com"
PORT = 443
GET_URL  = "https://contract.mexc.com/api/v1/contract/detail"
POST_URL = "https://contract.mexc.com/api/v1/private/order/submit"  # ожидаем 401/Signature error, но не timeout

def step(name, fn):
    print(f"\n-- {name} --")
    try:
        t0 = time.time()
        out = fn()
        dt = (time.time()-t0)*1000
        print(f"OK ({dt:.0f} ms) :: {out}")
    except Exception as e:
        print("FAIL ::", repr(e))

def dns():
    return socket.getaddrinfo(HOST, PORT)

def tcp_tls():
    ctx = ssl.create_default_context()
    s = socket.create_connection((HOST, PORT), timeout=8)
    tls = ctx.wrap_socket(s, server_hostname=HOST)
    tls.settimeout(8)
    tls.do_handshake()
    tls.close()
    return "TLS handshake ok"

def http_get():
    r = requests.get(GET_URL, timeout=8)
    return f"GET {r.status_code} len={len(r.content)}"

def http_post():
    # без подписи → ждём быстрый 4xx. если тут timeout — блокировка POST
    r = requests.post(POST_URL, timeout=8, data={})
    return f"POST {r.status_code} len={len(r.content)}"

if __name__ == "__main__":
    step("DNS", dns)
    step("TCP+TLS", tcp_tls)
    step("HTTP GET", http_get)
    step("HTTP POST (без подписи)", http_post)
    print("\nЕсли GET=OK, а POST=timeout → блокирует антивирус/фаервол/провайдер POST на contract.mexc.com.")
