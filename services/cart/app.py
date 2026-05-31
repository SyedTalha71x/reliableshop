# services/cart/app.py
import time
import random
import logging
import json
import os
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from dotenv import load_dotenv
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_config import db

load_dotenv()


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": "cart",
            "message": record.getMessage(),
        }
        if hasattr(record, 'trace_id'):
            log_data["trace_id"] = record.trace_id
        return json.dumps(log_data)


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("cart")
logger.addHandler(handler)
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

resource = Resource.create({
    "service.name": "cart-service",
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
tracer = trace.get_tracer("cart-service")

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

CART_ITEMS_ADDED = Counter("cart_items_added_total", "Items added to cart")
CART_ITEMS_REMOVED = Counter("cart_items_removed_total", "Items removed from cart")
CART_SIZE = Gauge("cart_active_sessions", "Active cart sessions")
CHECKOUT_LATENCY = Histogram("cart_checkout_duration_seconds", "Checkout processing time",
                              buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
ABANDONED_CARTS = Counter("cart_abandoned_total", "Abandoned carts")
DB_QUERY_LATENCY = Histogram("cart_db_query_duration_seconds", "Database query latency",
                              buckets=[0.01, 0.05, 0.1, 0.5, 1.0])


def get_user_cart(user_id):
    """Return the user's cart items as a list of plain dicts."""
    with db.get_cursor() as cur:
        cur.execute("""
            SELECT product_id, quantity, added_at
            FROM cart_items
            WHERE user_id = %s
            ORDER BY added_at DESC
        """, (user_id,))
        # FIX #1: Convert RealDictRow objects to plain dicts so jsonify()
        # can serialize them without raising a TypeError.
        return [dict(row) for row in cur.fetchall()]


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/health")
def health():
    try:
        with db.get_cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify({"status": "ok", "service": "cart", "database": "connected"})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "degraded", "service": "cart", "database": "disconnected"}), 503


@app.route("/cart/<user_id>/add", methods=["POST"])
def add_to_cart(user_id):
    start_time = time.time()
    with tracer.start_as_current_span("add_to_cart") as span:
        span.set_attribute("user.id", user_id)
        data = request.get_json() or {}
        product_id = data.get("product_id")
        quantity = data.get("quantity", 1)

        if not product_id:
            return jsonify({"error": "product_id is required"}), 400

        try:
            with db.get_cursor() as cur:
                cur.execute("""
                    INSERT INTO carts (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET updated_at = CURRENT_TIMESTAMP
                """, (user_id,))

                cur.execute("""
                    INSERT INTO cart_items (user_id, product_id, quantity)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, product_id)
                    DO UPDATE SET quantity = cart_items.quantity + EXCLUDED.quantity
                    RETURNING quantity
                """, (user_id, product_id, quantity))

                # FIX #2: Store fetchone() result once. The previous version used
                # isinstance(result, dict) which is always False for RealDictRow
                # (it's a dict subclass but the check was unreliable depending on
                # psycopg2 version). Always access by key with dict_cursor=True.
                row = cur.fetchone()
                new_quantity = row['quantity'] if row else quantity

            CART_ITEMS_ADDED.inc()
            DB_QUERY_LATENCY.observe(time.time() - start_time)
            logger.info(f"Item {product_id} added to cart for user {user_id}, quantity: {new_quantity}")

            cart_items = get_user_cart(user_id)
            return jsonify({"cart": cart_items, "message": "Item added successfully"})

        except Exception as e:
            logger.error(f"Error adding to cart: {e}")
            return jsonify({"error": "Database error occurred"}), 500


@app.route("/cart/<user_id>", methods=["GET"])
def get_cart(user_id):
    start_time = time.time()
    with tracer.start_as_current_span("get_cart") as span:
        span.set_attribute("user.id", user_id)

        try:
            cart_items = get_user_cart(user_id)
            DB_QUERY_LATENCY.observe(time.time() - start_time)

            with db.get_cursor() as cur:
                cur.execute("SELECT COUNT(DISTINCT user_id) FROM carts")
                # FIX #2 (cont): Same reliable single-fetchone pattern.
                row = cur.fetchone()
                count = row['count'] if row else 0
                CART_SIZE.set(count)

            return jsonify({
                "user_id": user_id,
                "items": cart_items,
                "total_items": len(cart_items)
            })
        except Exception as e:
            logger.error(f"Error getting cart: {e}")
            return jsonify({"error": "Database error occurred"}), 500


@app.route("/cart/<user_id>/remove", methods=["POST"])
def remove_from_cart(user_id):
    start_time = time.time()
    with tracer.start_as_current_span("remove_from_cart") as span:
        span.set_attribute("user.id", user_id)
        data = request.get_json() or {}
        product_id = data.get("product_id")
        quantity = data.get("quantity")

        if not product_id:
            return jsonify({"error": "product_id is required"}), 400

        try:
            with db.get_cursor() as cur:
                if quantity is None or quantity <= 0:
                    cur.execute("""
                        DELETE FROM cart_items
                        WHERE user_id = %s AND product_id = %s
                        RETURNING product_id
                    """, (user_id, product_id))
                else:
                    cur.execute("""
                        UPDATE cart_items
                        SET quantity = quantity - %s
                        WHERE user_id = %s AND product_id = %s
                        AND quantity >= %s
                        RETURNING quantity
                    """, (quantity, user_id, product_id, quantity))

                # FIX #3: Check rowcount to detect silent no-ops. If the item
                # didn't exist or quantity guard failed, return 404 instead of
                # a misleading 200 success response.
                if cur.rowcount == 0:
                    return jsonify({"error": "Item not found in cart or insufficient quantity"}), 404

                cur.execute("SELECT COUNT(*) FROM cart_items WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                count = row['count'] if row else 0

                if count == 0:
                    cur.execute("DELETE FROM carts WHERE user_id = %s", (user_id,))

            CART_ITEMS_REMOVED.inc()
            DB_QUERY_LATENCY.observe(time.time() - start_time)
            logger.info(f"Removed product {product_id} from cart for user {user_id}")

            cart_items = get_user_cart(user_id)
            return jsonify({"cart": cart_items, "message": "Item removed successfully"})

        except Exception as e:
            logger.error(f"Error removing from cart: {e}")
            return jsonify({"error": "Database error occurred"}), 500


@app.route("/cart/<user_id>/checkout", methods=["POST"])
def checkout(user_id):
    start = time.time()
    with tracer.start_as_current_span("checkout") as span:
        span.set_attribute("user.id", user_id)

        try:
            cart_items = get_user_cart(user_id)

            if not cart_items:
                return jsonify({"error": "Cart is empty"}), 400

            time.sleep(random.uniform(0.2, 1.5))

            if random.random() < 0.10:
                ABANDONED_CARTS.inc()
                CHECKOUT_LATENCY.observe(time.time() - start)
                logger.warning(f"Cart abandoned by user {user_id}")
                return jsonify({"status": "timeout", "message": "Session expired"}), 408

            with db.get_cursor() as cur:
                cur.execute("""
                    SELECT product_id, quantity
                    FROM cart_items
                    WHERE user_id = %s
                """, (user_id,))
                # FIX #1 (cont): Convert rows to plain dicts for JSON serialization.
                checked_out_items = [dict(row) for row in cur.fetchall()]

                cur.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM carts WHERE user_id = %s", (user_id,))

            CHECKOUT_LATENCY.observe(time.time() - start)
            logger.info(f"Checkout complete for user {user_id}, {len(checked_out_items)} items")

            return jsonify({
                "status": "checked_out",
                "items": checked_out_items,
                "total_items": len(checked_out_items)
            })

        except Exception as e:
            logger.error(f"Checkout error: {e}")
            return jsonify({"error": "Database error during checkout"}), 500


if __name__ == "__main__":
    # FIX #4: before_first_request removed in Flask 2.3. Initialize explicitly.
    with app.app_context():
        try:
            db.init_tables()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    port = int(os.getenv('CART_PORT', 5004))
    app.run(host="0.0.0.0", port=port, debug=False)