"""
Insight Demo Gateway — Python Flask API Gateway
Calls demo-java-app downstream → creates distributed traces.

Endpoints:
  GET /                   — Gateway info
  GET /gateway/users      — Proxy to Java /api/users
  GET /gateway/orders     — Proxy to Java /api/orders
  GET /gateway/products   — Proxy to Java /api/products
  GET /gateway/all        — Aggregate: users + orders + products
  GET /health             — Health check

Auto-instrumented by OpenTelemetry Python agent.
Exports traces + metrics + logs via OTLP to Insight OTel Agent.
"""

import json
import logging
import os
import random
import time
import threading

import requests
from flask import Flask, jsonify

# ─── Configuration ───

JAVA_APP_URL = os.getenv("JAVA_APP_URL", "http://demo-java-app:8090")
APP_PORT = int(os.getenv("APP_PORT", "8091"))

# Setup logging — OTel Python agent auto-captures these
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("demo-gateway")

app = Flask(__name__)

# ─── Stats ───
stats = {"requests": 0, "errors": 0, "upstream_calls": 0}


# ─── Helper: Call Java App ───

def call_java_app(path: str) -> dict:
    """Call downstream Java app and return response."""
    url = f"{JAVA_APP_URL}{path}"
    stats["upstream_calls"] += 1
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return {"status": resp.status_code, "data": resp.json()}
    except requests.exceptions.Timeout:
        logger.error(f"Upstream timeout: {url}")
        stats["errors"] += 1
        return {"status": 504, "error": "Gateway Timeout", "message": f"Upstream {path} timed out"}
    except requests.exceptions.ConnectionError:
        logger.error(f"Upstream connection failed: {url}")
        stats["errors"] += 1
        return {"status": 502, "error": "Bad Gateway", "message": f"Cannot reach upstream {path}"}
    except Exception as e:
        logger.error(f"Upstream error: {url} → {e}")
        stats["errors"] += 1
        return {"status": 500, "error": str(e)}


def simulate_processing(min_ms=10, max_ms=50):
    """Simulate gateway processing overhead."""
    delay = random.randint(min_ms, max_ms) / 1000.0
    time.sleep(delay)


# ─── Routes ───

@app.route("/")
def root():
    logger.info("GET / — gateway info")
    return jsonify({
        "service": "demo-gateway",
        "type": "api-gateway",
        "upstream": JAVA_APP_URL,
        "stats": stats,
    })


@app.route("/gateway/users")
def gateway_users():
    stats["requests"] += 1
    logger.info("GET /gateway/users — proxying to Java app")
    simulate_processing(20, 60)

    result = call_java_app("/api/users")

    # Gateway enrichment: add metadata
    if "data" in result:
        result["gateway"] = "demo-gateway"
        result["enriched"] = True
        logger.info(f"Users response enriched: {result['data'].get('total', 0)} users")
    else:
        logger.warning(f"Users upstream returned error: {result.get('error')}")

    status = result.pop("status", 200)
    return jsonify(result), status


@app.route("/gateway/orders")
def gateway_orders():
    stats["requests"] += 1
    logger.info("GET /gateway/orders — proxying to Java app")
    simulate_processing(30, 80)

    # 10% chance of gateway-level rate limiting
    if random.random() < 0.10:
        logger.warning("Rate limit exceeded for /gateway/orders — rejecting request")
        stats["errors"] += 1
        return jsonify({"error": "Too Many Requests", "message": "Gateway rate limit exceeded"}), 429

    result = call_java_app("/api/orders")

    if "data" in result:
        result["gateway"] = "demo-gateway"
        logger.info(f"Orders response: {result['data'].get('total', 0)} orders")
    else:
        logger.error(f"Orders upstream error: {result.get('error')}")

    status = result.pop("status", 200)
    return jsonify(result), status


@app.route("/gateway/products")
def gateway_products():
    stats["requests"] += 1
    logger.info("GET /gateway/products — proxying to Java app")
    simulate_processing(15, 40)

    result = call_java_app("/api/products")

    if "data" in result:
        result["gateway"] = "demo-gateway"
        logger.info(f"Products response: {result['data'].get('total', 0)} products")
    else:
        logger.warning(f"Products upstream error: {result.get('error')}")

    status = result.pop("status", 200)
    return jsonify(result), status


@app.route("/gateway/all")
def gateway_all():
    """Aggregate endpoint — calls all 3 Java endpoints in sequence."""
    stats["requests"] += 1
    logger.info("GET /gateway/all — aggregating all data from Java app")
    simulate_processing(10, 30)

    users = call_java_app("/api/users")
    orders = call_java_app("/api/orders")
    products = call_java_app("/api/products")

    has_errors = any("error" in r for r in [users, orders, products])
    if has_errors:
        logger.warning("Aggregate response has partial failures")

    return jsonify({
        "gateway": "demo-gateway",
        "users": users.get("data"),
        "orders": orders.get("data"),
        "products": products.get("data"),
        "errors": [r.get("error") for r in [users, orders, products] if "error" in r],
    })


@app.route("/health")
def health():
    return jsonify({"status": "UP", "service": "demo-gateway"})


# ─── Traffic Generator ───

def traffic_generator():
    """Background thread: periodically calls gateway endpoints to generate traces."""
    time.sleep(10)  # Wait for app to start
    logger.info("Traffic generator started (every 4s)")

    endpoints = ["/gateway/users", "/gateway/orders", "/gateway/products", "/gateway/all"]

    while True:
        try:
            ep = random.choice(endpoints)
            resp = requests.get(f"http://localhost:{APP_PORT}{ep}", timeout=15)
            logger.info(f"[TrafficGen] {ep} → {resp.status_code}")
        except Exception as e:
            logger.warning(f"[TrafficGen] failed: {e}")
        time.sleep(random.uniform(3, 5))


# ─── Main ───

if __name__ == "__main__":
    # Start traffic generator in background
    t = threading.Thread(target=traffic_generator, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=APP_PORT, debug=False)
