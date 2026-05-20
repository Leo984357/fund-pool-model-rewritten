import time, math, functools, random
from datetime import datetime, timedelta
from typing import Iterable, List

def log(*args):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}]", *args)

def today_ymd():
    return datetime.now().strftime("%Y-%m-%d")

def ymd(d):
    if isinstance(d, str): return d[:10]
    return d.strftime("%Y-%m-%d")

def chunked(seq: Iterable, n: int) -> Iterable[List]:
    buf = []
    for x in seq:
        buf.append(x)
        if len(buf) == n:
            yield buf; buf = []
    if buf: yield buf

def retry(exceptions=(Exception,), tries=3, base_delay=1.0, jitter=0.2):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **k):
            for i in range(tries):
                try:
                    return fn(*a, **k)
                except exceptions as e:
                    if i == tries - 1: raise
                    sleep = base_delay * (2 ** i) + random.random() * jitter
                    log(f"重试 {fn.__name__}：{e}，sleep {sleep:.1f}s")
                    time.sleep(sleep)
        return wrapper
    return deco
