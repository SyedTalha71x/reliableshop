# services/products/app.py
import time
import random
import logging
import json
import os
# FIX #1: request was missing from the Flask import. list_products() calls
# request.args.get('category') at runtime, which raises a NameError without it.
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from dotenv import load_dotenv

load_dotenv()


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": "products",
            "message": record.getMessage(),
        })


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("products")
logger.addHandler(handler)
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

resource = Resource.create({
    "service.name": "products-service",
    "service.namespace": "reliableshop",
    "deployment.environment": "production"
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(
        endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://tempo:4317'),
        insecure=True
    )
))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("products-service")

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

CATALOG_REQUESTS = Counter("products_catalog_requests_total", "Catalog browse requests", ["category"])
SEARCH_LATENCY = Histogram("products_search_duration_seconds", "Product search latency",
                           buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25])
CACHE_HITS = Counter("products_cache_hits_total", "Redis cache hits")
CACHE_MISSES = Counter("products_cache_misses_total", "Redis cache misses")

PRODUCTS = [
    {"id": 1, "name": "Laptop",       "price": 999.99, "category": "electronics", "stock": 50},
    {"id": 2, "name": "Headphones",   "price": 149.99, "category": "electronics", "stock": 150},
    {"id": 3, "name": "T-Shirt",      "price":  29.99, "category": "clothing",    "stock": 200},
    {"id": 4, "name": "Coffee Maker", "price":  79.99, "category": "kitchen",     "stock": 75},
    {"id": 5, "name": "Smartphone",   "price": 699.99, "category": "electronics", "stock": 30},
    {"id": 6, "name": "Jeans",        "price":  59.99, "category": "clothing",    "stock": 100},
]


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "products"})


@app.route("/products", methods=["GET"])
def list_products():
    start = time.time()
    with tracer.start_as_current_span("list_products"):
        # Simulate cache hit/miss
        if random.random() > 0.3:
            CACHE_HITS.inc()
            time.sleep(random.uniform(0.002, 0.01))
        else:
            CACHE_MISSES.inc()
            time.sleep(random.uniform(0.05, 0.15))

        category = request.args.get('category')
        if category:
            filtered_products = [p for p in PRODUCTS if p['category'] == category]
            CATALOG_REQUESTS.labels(category).inc()
        else:
            filtered_products = PRODUCTS
            CATALOG_REQUESTS.labels("all").inc()

        SEARCH_LATENCY.observe(time.time() - start)
        logger.info(f"Product catalog retrieved, {len(filtered_products)} products")
        return jsonify(filtered_products)


@app.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    start = time.time()
    with tracer.start_as_current_span("get_product") as span:
        span.set_attribute("product.id", product_id)
        time.sleep(random.uniform(0.005, 0.05))
        product = next((p for p in PRODUCTS if p["id"] == product_id), None)
        SEARCH_LATENCY.observe(time.time() - start)
        if not product:
            logger.warning(f"Product {product_id} not found")
            return jsonify({"error": "Not found"}), 404
        logger.info(f"Product {product_id} retrieved")
        return jsonify(product)


if __name__ == "__main__":
    port = int(os.getenv('PRODUCTS_PORT', 5003))
    app.run(host="0.0.0.0", port=port, debug=False)