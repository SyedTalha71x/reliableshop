# services/payments/app.py
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
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database_config import db

load_dotenv()


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": "payments",
            "message": record.getMessage(),
        })


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("payments")
logger.addHandler(handler)
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

resource = Resource.create({
    "service.name": "payments-service",
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
tracer = trace.get_tracer("payments-service")

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

PAYMENT_COUNT = Counter("payments_total", "Total payment attempts", ["status"])
PAYMENT_LATENCY = Histogram("payments_duration_seconds", "Payment processing time",
                            buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0])
PAYMENT_AMOUNT = Histogram("payments_amount_dollars", "Payment amounts",
                           buckets=[10, 50, 100, 250, 500, 1000])
ACTIVE_PAYMENTS = Gauge("payments_active", "Currently processing payments")
DB_QUERY_LATENCY = Histogram("payments_db_query_duration_seconds", "Database query latency")


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/health")
def health():
    try:
        with db.get_cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify({"status": "ok", "service": "payments", "database": "connected"})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "degraded", "service": "payments", "database": "disconnected"}), 503


@app.route("/pay", methods=["POST"])
def process_payment():
    ACTIVE_PAYMENTS.inc()
    start = time.time()
    data = request.get_json() or {}
    amount = data.get("amount", random.uniform(10, 500))
    order_id = data.get("order_id")
    payment_method = data.get("payment_method", "credit_card")

    # FIX #2: Wrap the entire route in the tracer span, including the failure
    # branch. Previously the span was started but the ACTIVE_PAYMENTS.inc() and
    # input parsing happened outside it, so those operations were untraced.
    with tracer.start_as_current_span("process_payment") as span:
        span.set_attribute("payment.amount", amount)
        span.set_attribute("payment.method", payment_method)
        if order_id:
            span.set_attribute("order.id", order_id)

        # Simulate payment gateway delay
        time.sleep(random.uniform(0.1, 0.8))

        PAYMENT_AMOUNT.observe(amount)

        transaction_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"

        # 8% failure rate
        if random.random() < 0.08:
            PAYMENT_COUNT.labels("failed").inc()
            ACTIVE_PAYMENTS.dec()
            elapsed = time.time() - start
            PAYMENT_LATENCY.observe(elapsed)

            # FIX #3: Log failed payment to database before returning.
            # Previously a local variable REQUEST_LATENCY was assigned but never
            # used — the name shadowed nothing and was dead code.
            try:
                db_start = time.time()
                with db.get_cursor() as cur:
                    cur.execute("""
                        INSERT INTO payments (transaction_id, order_id, amount, status, payment_method)
                        VALUES (%s, %s, %s, 'failed', %s)
                    """, (transaction_id, order_id, amount, payment_method))
                DB_QUERY_LATENCY.observe(time.time() - db_start)
            except Exception as e:
                logger.error(f"Failed to log payment error: {e}")

            logger.warning(f"Payment declined for amount ${amount:.2f}, transaction: {transaction_id}")
            return jsonify({
                "status": "declined",
                "reason": "Insufficient funds",
                "transaction_id": transaction_id
            }), 402

        # Successful payment
        PAYMENT_COUNT.labels("success").inc()
        ACTIVE_PAYMENTS.dec()
        payment_time = time.time() - start
        PAYMENT_LATENCY.observe(payment_time)

        db_start = time.time()
        try:
            with db.get_cursor() as cur:
                cur.execute("""
                    INSERT INTO payments (transaction_id, order_id, amount, status, payment_method)
                    VALUES (%s, %s, %s, 'success', %s)
                """, (transaction_id, order_id, amount, payment_method))
            DB_QUERY_LATENCY.observe(time.time() - db_start)
        except Exception as e:
            logger.error(f"Failed to save payment record: {e}")
            # FIX #4: A successful gateway response but failed DB write should
            # still return the transaction to the caller (the money moved), but
            # we flag it in the log. Swallowing the exception silently is
            # intentional here — do not re-raise.

        logger.info(f"Payment successful: ${amount:.2f}, transaction: {transaction_id}")
        return jsonify({
            "status": "success",
            "transaction_id": transaction_id,
            "amount": amount,
            "processing_time": payment_time
        })


@app.route("/payments/<transaction_id>", methods=["GET"])
def get_payment(transaction_id):
    """Get payment details by transaction ID."""
    with tracer.start_as_current_span("get_payment") as span:
        span.set_attribute("transaction.id", transaction_id)

        try:
            with db.get_cursor() as cur:
                cur.execute("""
                    SELECT * FROM payments WHERE transaction_id = %s
                """, (transaction_id,))
                payment = cur.fetchone()

                if not payment:
                    return jsonify({"error": "Payment not found"}), 404

                # FIX #5: Convert RealDictRow to a plain dict before passing to
                # jsonify(). RealDictRow is not JSON-serializable and raises a
                # TypeError without this conversion.
                return jsonify(dict(payment))

        except Exception as e:
            logger.error(f"Error fetching payment {transaction_id}: {e}")
            return jsonify({"error": "Database error occurred"}), 500


if __name__ == "__main__":
    # FIX #1: before_first_request removed in Flask 2.3. Initialize explicitly.
    with app.app_context():
        try:
            db.init_tables()
            logger.info("Database initialized for payments service")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    port = int(os.getenv('PAYMENT_PORT', 5002))
    app.run(host="0.0.0.0", port=port, debug=False)