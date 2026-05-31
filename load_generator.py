#!/usr/bin/env python3
"""
ReliableShop Load Generator
Simulates realistic traffic across all services including
DB-backed routes: order listing, payment stats, cart history.

Usage:
    pip install requests
    python load_generator.py
"""
import time
import random
import threading
import requests
import sys

BASE = {
    "orders":   "http://localhost:5001",
    "payments": "http://localhost:5002",
    "products": "http://localhost:5003",
    "cart":     "http://localhost:5004",
}

USERS      = [f"user_{i}" for i in range(1, 31)]
CATEGORIES = ["electronics", "clothing", "kitchen", "sports", "home", "books"]

# Track created orders so GET /orders/:id can be tested
created_orders = []
_lock = threading.Lock()

def safe_post(url, **kwargs):
    try:
        return requests.post(url, timeout=5, **kwargs)
    except Exception:
        return None

def safe_get(url, **kwargs):
    try:
        return requests.get(url, timeout=5, **kwargs)
    except Exception:
        return None

# ── Traffic patterns ─────────────────────────────────────────────

def browse_products():
    """70% browse all, 30% filter by category, 50% get single product."""
    if random.random() < 0.3:
        safe_get(f"{BASE['products']}/products",
                 params={"category": random.choice(CATEGORIES)})
    else:
        safe_get(f"{BASE['products']}/products")

    if random.random() < 0.5:
        safe_get(f"{BASE['products']}/products/{random.randint(1, 8)}")

def create_order():
    """Create order + optionally fetch it back (tests cache vs DB)."""
    r = safe_post(f"{BASE['orders']}/orders",
                  json={"product_id": random.randint(1, 8),
                        "qty": random.randint(1, 5)})
    if r and r.status_code == 201:
        oid = r.json().get("order_id")
        if oid:
            with _lock:
                created_orders.append(oid)
                if len(created_orders) > 200:
                    created_orders.pop(0)

def fetch_order():
    """Fetch an existing order (hits Redis cache then DB)."""
    with _lock:
        if not created_orders:
            return
        oid = random.choice(created_orders)
    safe_get(f"{BASE['orders']}/orders/{oid}")

def list_orders():
    safe_get(f"{BASE['orders']}/orders", params={"page": 1, "per_page": 10})

def process_payment():
    r = safe_post(f"{BASE['payments']}/pay",
                  json={"amount": round(random.uniform(5, 800), 2),
                        "payment_method": random.choice(["card", "bank_transfer", "wallet"])})
    if r and r.status_code == 200:
        txn = r.json().get("transaction_id")
        if txn and random.random() < 0.3:
            # Fetch transaction back — tests cache
            safe_get(f"{BASE['payments']}/payments/{txn}")

def payment_stats():
    safe_get(f"{BASE['payments']}/payments/stats")

def cart_flow():
    """Full cart flow: add items → checkout (or abandon)."""
    user = random.choice(USERS)
    products = random.sample(range(1, 9), k=random.randint(1, 4))
    for pid in products:
        safe_post(f"{BASE['cart']}/cart/{user}/add",
                  json={"product_id": pid})
        time.sleep(random.uniform(0.05, 0.2))

    if random.random() < 0.75:
        safe_post(f"{BASE['cart']}/cart/{user}/checkout")

def view_cart():
    safe_get(f"{BASE['cart']}/cart/{random.choice(USERS)}")

def cart_stats():
    safe_get(f"{BASE['cart']}/cart/stats")

def cart_history():
    safe_get(f"{BASE['cart']}/cart/history/{random.choice(USERS)}")

def check_health():
    for svc, base in BASE.items():
        safe_get(f"{base}/health")

# ── Weighted traffic mix ─────────────────────────────────────────
TRAFFIC = [
    (browse_products, 25),   # most common — browsing
    (create_order,    15),   # ordering
    (fetch_order,     12),   # checking order status
    (process_payment, 15),   # payments
    (cart_flow,       15),   # add to cart + checkout
    (view_cart,        8),   # view cart
    (list_orders,      5),   # list orders (pagination)
    (payment_stats,    2),   # stats endpoints
    (cart_stats,       2),   # cart analytics
    (cart_history,     2),   # user history
    (check_health,     1),   # health polling
]

# Build weighted pool
POOL = []
for fn, weight in TRAFFIC:
    POOL.extend([fn] * weight)

def worker():
    fn = random.choice(POOL)
    try:
        fn()
    except Exception:
        pass

def run():
    print("=" * 55)
    print("  ReliableShop Load Generator")
    print("  Ctrl+C to stop")
    print("=" * 55)
    print()

    # Warm up — wait for services
    print("Waiting for services to be ready...")
    for _ in range(10):
        try:
            r = requests.get(f"{BASE['orders']}/health", timeout=2)
            if r.status_code == 200:
                print("✅ Services ready — starting traffic\n")
                break
        except Exception:
            pass
        time.sleep(2)

    req_count = 0
    start_time = time.time()

    while True:
        threads = [threading.Thread(target=worker) for _ in range(random.randint(2, 6))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        req_count += len(threads)
        elapsed = int(time.time() - start_time)

        if req_count % 50 == 0:
            rps = round(req_count / max(elapsed, 1), 1)
            print(f"  [{elapsed:>5}s] {req_count:>6} requests sent  |  ~{rps} req/s")

        time.sleep(random.uniform(0.3, 1.5))

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\nLoad generator stopped.")
        sys.exit(0)