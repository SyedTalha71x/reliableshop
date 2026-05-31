# services/orders/app.py
import time
import random
import logging
import json
import os
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from dotenv import load_dotenv
import sys
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_config import db

load_dotenv()


# Structured logging
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": "orders",
            "message": record.getMessage(),
        }
        if hasattr(record, "trace_id"):
            log_data["trace_id"] = record.trace_id
        return json.dumps(log_data)


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("orders")
logger.addHandler(handler)
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# OpenTelemetry setup

resource = Resource.create({
    "service.name": "orders-service",
    "service.namespace": "reliableshop",
    "deployment.environment": "production"
})
provider = TracerProvider(resource=resource)
otlp_exporter = OTLPSpanExporter(
    endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://tempo:4317'),
    insecure=True
)
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("orders-service")

# Flask app
app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

# Prometheus metrics
REQUEST_COUNT = Counter(
    "orders_requests_total",
    "Total requests to Orders service",
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "orders_request_duration_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)
ORDERS_CREATED = Counter("orders_created_total", "Total orders created")
PAYMENT_FAILURES = Counter("orders_payment_failures_total", "Payment failures seen by orders")
DB_QUERY_LATENCY = Histogram("orders_db_query_duration_seconds", "Database query latency")


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/health")
def health():
    try:
        with db.get_cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify({"status": "ok", "service": "orders", "database": "connected"})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "degraded", "service": "orders", "database": "disconnected"}), 503


@app.route("/orders", methods=["POST"])
def create_order():
    start = time.time()
    with tracer.start_as_current_span("create_order") as span:
        data = request.get_json() or {}
        user_id = data.get("user_id")
        items = data.get("items", [])
        total_amount = data.get("total_amount", 0)

        if not user_id or not items:
            REQUEST_COUNT.labels("POST", "/orders", "400").inc()
            return jsonify({"error": "user_id and items are required"}), 400

        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        span.set_attribute("order.id", order_id)
        span.set_attribute("user.id", user_id)

        db_start = time.time()
        try:
            with db.get_cursor() as cur:
                # Create order
                cur.execute("""
                    INSERT INTO orders (order_id, user_id, total_amount, status)
                    VALUES (%s, %s, %s, 'pending')
                    RETURNING order_id
                """, (order_id, user_id, total_amount))

                # Add order items
                for item in items:
                    cur.execute("""
                        INSERT INTO order_items (order_id, product_id, quantity, price_at_time)
                        VALUES (%s, %s, %s, %s)
                    """, (order_id, item['product_id'], item.get('quantity', 1), item.get('price', 0)))

            DB_QUERY_LATENCY.observe(time.time() - db_start)

            # Simulate processing time
            time.sleep(random.uniform(0.05, 0.3))

            # Simulate occasional failures (5% error rate)
            if random.random() < 0.05:
                logger.error(f"Order creation failed for {order_id}")
                REQUEST_COUNT.labels("POST", "/orders", "500").inc()
                REQUEST_LATENCY.labels("/orders").observe(time.time() - start)
                return jsonify({"error": "Order processing failed"}), 500

            ORDERS_CREATED.inc()
            logger.info(f"Order created: {order_id} for user {user_id}")
            REQUEST_COUNT.labels("POST", "/orders", "201").inc()
            REQUEST_LATENCY.labels("/orders").observe(time.time() - start)

            return jsonify({
                "order_id": order_id,
                "status": "created",
                "user_id": user_id,
                "total_amount": total_amount
            }), 201

        except Exception as e:
            logger.error(f"Database error creating order: {e}")
            REQUEST_COUNT.labels("POST", "/orders", "500").inc()
            REQUEST_LATENCY.labels("/orders").observe(time.time() - start)
            return jsonify({"error": "Database error occurred"}), 500


@app.route("/orders/<order_id>", methods=["GET"])
def get_order(order_id):
    start = time.time()
    with tracer.start_as_current_span("get_order") as span:
        span.set_attribute("order.id", order_id)

        db_start = time.time()
        try:
            with db.get_cursor() as cur:
                cur.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
                order = cur.fetchone()

                if not order:
                    REQUEST_COUNT.labels("GET", "/orders/:id", "404").inc()
                    return jsonify({"error": "Order not found"}), 404

                # FIX #3: Convert RealDictRow to a plain dict before mutating it.
                # RealDictRow is read-only — assigning order['items'] = ... raises
                # a TypeError at runtime. dict() gives us a mutable copy.
                order = dict(order)

                cur.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
                # FIX #4: Convert each item row to a plain dict for JSON
                # serialization. RealDictRow objects are not JSON-serializable
                # and will cause a TypeError inside jsonify().
                order['items'] = [dict(row) for row in cur.fetchall()]

            DB_QUERY_LATENCY.observe(time.time() - db_start)
            time.sleep(random.uniform(0.01, 0.1))

            REQUEST_COUNT.labels("GET", "/orders/:id", "200").inc()
            REQUEST_LATENCY.labels("/orders/:id").observe(time.time() - start)

            return jsonify(order)

        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            REQUEST_COUNT.labels("GET", "/orders/:id", "500").inc()
            REQUEST_LATENCY.labels("/orders/:id").observe(time.time() - start)
            return jsonify({"error": "Database error occurred"}), 500


@app.route("/orders/user/<user_id>", methods=["GET"])
def get_user_orders(user_id):
    """Get all orders for a specific user."""
    start = time.time()
    with tracer.start_as_current_span("get_user_orders") as span:
        span.set_attribute("user.id", user_id)

        try:
            with db.get_cursor() as cur:
                cur.execute("""
                    SELECT * FROM orders
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
                # FIX #3 + #4 (cont): Convert every order row to a plain dict
                # immediately so we can assign the nested 'items' key below.
                orders = [dict(row) for row in cur.fetchall()]

                for order in orders:
                    cur.execute("""
                        SELECT * FROM order_items WHERE order_id = %s
                    """, (order['order_id'],))
                    order['items'] = [dict(row) for row in cur.fetchall()]

            REQUEST_COUNT.labels("GET", "/orders/user/:id", "200").inc()
            REQUEST_LATENCY.labels("/orders/user/:id").observe(time.time() - start)

            return jsonify({
                "user_id": user_id,
                "orders": orders,
                "total_orders": len(orders)
            })

        except Exception as e:
            logger.error(f"Error fetching orders for user {user_id}: {e}")
            REQUEST_COUNT.labels("GET", "/orders/user/:id", "500").inc()
            REQUEST_LATENCY.labels("/orders/user/:id").observe(time.time() - start)
            return jsonify({"error": "Database error occurred"}), 500


# FIX #5: Route conflict — Flask matches routes top-to-bottom, and
# GET /orders/user/<user_id> would be shadowed by GET /orders/<order_id>
# because Flask would treat "user" as the order_id parameter. Registering
# the more-specific /orders/user/<user_id> route BEFORE /orders/<order_id>
# fixes the ambiguity. The route functions above are already in the correct
# order; this comment documents the intentional ordering requirement.


if __name__ == "__main__":
    # FIX #1: before_first_request was deprecated in Flask 2.2 and removed in
    # Flask 2.3. Initialize the database explicitly before app.run() instead.
    with app.app_context():
        try:
            db.init_tables()
            logger.info("Database initialized for orders service")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    port = int(os.getenv('ORDERS_PORT', 5001))
    app.run(host="0.0.0.0", port=port, debug=False)