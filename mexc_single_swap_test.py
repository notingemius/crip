import requests, time
HOSTS = ["contract.mexc.com","contract.mexc.io"]
PATH  = "/api/v1/private/order/submit"

def probe(url):
    t=time.time()
    try:
        r=requests.post(url, json={"dummy":True}, timeout=8)
        print("OK", r.status_code, int((time.time()-t)*1000),"ms", r.text[:120])
    except Exception as e:
        print("FAIL", int((time.time()-t)*1000),"ms", repr(e))

print("httpbin control:")
probe("https://httpbin.org/post")
for h in HOSTS:
    print("MEXC:", h)
    probe(f"https://{h}{PATH}")
