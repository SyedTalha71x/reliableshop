# 🛒 ReliableShop — Full-Stack Observability Platform
> A production-grade e-commerce observability platform demonstrating the **three pillars of observability** — Metrics, Logs, and Traces — across a microservices architecture using industry-standard open-source tooling.
[![Made With](https://img.shields.io/badge/Made%20With-Python%20%7C%20Flask-blue?style=flat-square)](https://flask.palletsprojects.com)
[![Prometheus](https://img.shields.io/badge/Metrics-Prometheus-E6522C?style=flat-square&logo=prometheus)](https://prometheus.io)
[![Grafana](https://img.shields.io/badge/Dashboards-Grafana-F46800?style=flat-square&logo=grafana)](https://grafana.com)
[![Docker](https://img.shields.io/badge/Orchestration-Docker%20Compose-2496ED?style=flat-square&logo=docker)](https://docker.com)
[![OpenTelemetry](https://img.shields.io/badge/Tracing-OpenTelemetry-425CC7?style=flat-square)](https://opentelemetry.io)
---
## 📌 What Is This Project?
ReliableShop simulates a real e-commerce backend with **4 Python microservices** (Orders, Payments, Products, Cart) fully instrumented with observability tooling that mirrors what companies like **Uber, Cloudflare, and Shopify** use in production.
The goal: demonstrate end-to-end observability — from a user placing an order to diagnosing why a payment is slow — using only open-source tools.
---
## 🏗️ Architecture
```
                        USER TRAFFIC
                             │
                             ▼
                    ┌─────────────────┐
                    │  NGINX (Port 80) │  ← Reverse Proxy + Metrics
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼                  ▼
   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
   │   Orders    │  │  Payments   │  │  Products   │  │    Cart     │
   │  :5001      │  │  :5002      │  │  :5003      │  │  :5004      │
   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
          │                │                │                │
          └────────────────┴────────────────┴────────────────┘
                                    │
                                    ▼
                           ┌──────────────┐
                           │  PostgreSQL  │
                           │  (Permanent) │
                           └──────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
   │ Prometheus  │          │    Loki     │          │    Tempo    │
   │  (Metrics)  │          │   (Logs)    │          │  (Traces)   │
   └──────┬──────┘          └──────┬──────┘          └──────┬──────┘
          └─────────────────────────┼─────────────────────────┘
                                    ▼
                           ┌─────────────────┐
                           │     Grafana     │  ← Unified Dashboard
                           └────────┬────────┘
                                    │
                           ┌─────────────────┐
                           │  Alertmanager   │  → Slack / Email
                           └─────────────────┘
```
---
## 🛠️ Tech Stack
### Microservices
| Service | Language | Port | Responsibility |
|---------|----------|------|----------------|
| Orders | Python/Flask | 5001 | Order lifecycle, CRUD, status tracking |
| Payments | Python/Flask | 5002 | Payment processing, revenue stats |
| Products | Python/Flask | 5003 | Product catalog, stock management |
| Cart | Python/Flask | 5004 | Session cart + checkout history |
### Databases
| Database | Purpose | Why |
|----------|---------|-----|
| PostgreSQL 15 | Permanent storage — orders, payments, products, checkout history | ACID compliant, relational |
### Observability Stack
| Tool | Version | Role |
|------|---------|------|
| Prometheus | v2.48.0 | Metrics collection (pull-based, 15s interval) |
| Grafana | v10.2.3 | Unified visualization — metrics, logs, traces |
| Loki | v2.9.3 | Log aggregation (label-based, cost-efficient) |
| Promtail | v2.9.3 | Log collection agent (Docker socket) |
| Tempo | v2.3.1 | Distributed tracing backend (OTLP receiver) |
| Alertmanager | v0.26.0 | Alert routing, deduplication, silencing |
| OpenTelemetry | SDK 1.22 | Vendor-neutral instrumentation |
| Node Exporter | v1.7.0 | Host-level metrics (CPU, RAM, disk) |
| cAdvisor | v0.47.2 | Container-level metrics |
| Postgres Exporter | latest | PostgreSQL metrics (connections, query stats) |
| NGINX Exporter | latest | Web server metrics (requests, connections) |
---
## ✨ Key Features
### Observability
- ✅ **Full metrics pipeline** — custom Prometheus metrics on every endpoint (RED method)
- ✅ **Structured JSON logging** — all services emit JSON logs with level, service, timestamp
- ✅ **Distributed tracing** — OpenTelemetry traces every request end-to-end via Tempo
- ✅ **Log-to-trace correlation** — click a log line in Grafana → jump directly to the trace
- ✅ **14 alert rules** — ServiceDown, HighErrorRate, HighLatency, PaymentFailure, DB alerts
- ✅ **Infrastructure monitoring** — host metrics, container metrics, DB metrics
### Application Design
- ✅ **Graceful degradation** — services respond with degraded status when DB is down
- ✅ **Realistic failure simulation** — 5% order failure, 8% payment decline, 10% cart timeout
- ✅ **Pagination** — order listing with page/per_page support
- ✅ **Business metrics** — revenue tracking, cart abandon rate, payment success rate
---
## 📊 Metrics Exposed
### Orders Service
```
orders_requests_total{method, endpoint, status}     # Request count by status code
orders_request_duration_seconds{endpoint}           # Latency histogram
orders_created_total                                # Business metric: orders placed
orders_db_errors_total                              # Database error count
```
### Payments Service
```
payments_total{status}                    # Success vs failed payments
payments_duration_seconds                 # Payment processing time histogram
payments_amount_dollars                   # Payment amount distribution
payments_active                           # Gauge: in-flight payments
payments_db_errors_total
```
### Products Service
```
products_catalog_requests_total{category} # Requests per category
products_search_duration_seconds          # Search latency histogram
products_stock_updates_total
```
### Cart Service
```
cart_items_added_total                    # Items added counter
cart_items_removed_total
cart_active_sessions                      # Gauge: active carts
cart_checkout_duration_seconds            # Checkout time histogram
cart_abandoned_total                      # Business metric: abandoned carts
cart_checkouts_completed_total
```
---
## 🚨 Alert Rules
| Alert | Condition | Severity | For |
|-------|-----------|----------|-----|
| ServiceDown | `up == 0` | Critical | 1m |
| HighErrorRate | Error rate > 5% | Critical | 2m |
| HighP99Latency | P99 > 1s | Warning | 3m |
| PaymentLatencyHigh | P95 > 2s | Critical | 2m |
| HighPaymentFailureRate | Failure > 10% | Critical | 2m |
| HighCartAbandonRate | Abandon > 20% | Warning | 5m |
| PostgresDown | `pg_up == 0` | Critical | 1m |
| HighCPUUsage | CPU > 80% | Warning | 5m |
| HighMemoryUsage | Memory > 85% | Warning | 5m |
| DiskSpaceLow | Disk < 15% | Critical | 10m |
---
## 🚀 Quick Start
### Prerequisites
- Docker Desktop (with Docker Compose)
- Python 3.11+
- 4GB RAM minimum (8GB recommended)
- Ports free: 80, 3000, 3100, 3200, 4317, 5001-5004, 5432, 9090, 9093, 9100
### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/reliableshop.git
cd reliableshop
```
### 2. Start the full stack
```bash
docker compose up --build -d
```
Wait ~30 seconds for all services to become healthy.
### 3. Verify everything is running
```bash
docker compose ps
# All containers should show "Up (healthy)"
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep health
# All should show "health": "up"
```
### 4. Generate traffic
```bash
pip install requests
python load_generator.py
```
### 5. Access dashboards
| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3000 | admin / admin123 |
| **Prometheus** | http://localhost:9090 | — |
| **Alertmanager** | http://localhost:9093 | — |
| **cAdvisor** | http://localhost:8080 | — |
---
## 📈 Grafana Setup
### Import pre-built dashboards
Go to Grafana → Dashboards → New → Import, use these IDs:
| ID | Dashboard | What It Shows |
|----|-----------|---------------|
| `1860` | Node Exporter Full | CPU, RAM, disk, network |
| `893` | Docker Monitoring | Container resource usage |
| `9628` | PostgreSQL | Connections, query duration, cache |
### Key PromQL queries to use
```promql
# Request rate per service
sum(rate(orders_requests_total[5m])) by (status)
# P99 latency
histogram_quantile(0.99, sum(rate(orders_request_duration_seconds_bucket[5m])) by (le))
# Payment success rate %
sum(rate(payments_total{status="success"}[5m])) / sum(rate(payments_total[5m])) * 100
# Cart abandon rate %
sum(rate(cart_abandoned_total[15m])) / (sum(rate(cart_abandoned_total[15m])) + sum(rate(cart_checkouts_completed_total[15m]))) * 100
# Active cart sessions
cart_active_sessions
# Container CPU usage
rate(container_cpu_usage_seconds_total{name=~".*-service"}[5m]) * 100
```
---
## 🔥 Chaos Engineering Tests
These tests prove the alerting and observability work end-to-end.
### Test 1 — Service Crash
```bash
# Stop orders service — triggers ServiceDown alert in ~2 minutes
docker compose stop orders
# Watch alert fire
watch -n 5 'curl -s http://localhost:9090/api/v1/alerts | python3 -m json.tool | grep -E "alertname|state"'
# Recover
docker compose start orders
```
### Test 2 — Database Failure
```bash
# Stop PostgreSQL — services degrade gracefully
docker compose stop postgres
# Health endpoint shows degraded state
curl http://localhost:5001/health
# {"database":"error","service":"orders","status":"degraded"}
# Recover
docker compose start postgres
```
### Test 3 — High Error Rate
```bash
# Flood orders endpoint — triggers HighErrorRate alert
for i in {1..200}; do
curl -s -X POST http://localhost:5001/orders \
    -H "Content-Type: application/json" \
-d '{"product_id": 1, "qty": 1}' > /dev/null &
done
wait
```
### Test 4 — Measure MTTR
```bash
START=$(date +%s)
docker compose stop payments
until curl -s http://localhost:5002/health 2>/dev/null | grep -q '"status":"ok"'; do
docker compose start payments 2>/dev/null
sleep 2
done
END=$(date +%s)
echo "Recovery time: $((END - START)) seconds"
```
---
## 📁 Project Structure
```
reliableshop/
├── services/
│   ├── orders/
│   │   ├── app.py              # Flask app + Prometheus metrics + OTel tracing
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── payments/
│   ├── products/
│   └── cart/
├── prometheus/
│   ├── prometheus.yml          # Scrape configs for all targets
│   └── rules/
│       └── alerts.yml          # Alert rules
├── grafana/
│   └── provisioning/
│       ├── datasources/        # Auto-configured Prometheus, Loki, Tempo
│       └── dashboards/
├── loki/
│   └── loki-config.yml         # Label-based log storage
├── promtail/
│   └── promtail-config.yml     # Docker log collection + JSON parsing
├── tempo/
│   └── tempo-config.yml        # OTLP receiver config
├── alertmanager/
│   └── alertmanager.yml        # Alert routing (Slack/email)
├── nginx/
│   └── nginx.conf              # Reverse proxy + stub_status
├── postgres/
│   └── init.sql                # DB init + user permissions
├── docker-compose.yml          # Services, volumes, healthchecks
├── load_generator.py           # Realistic traffic simulation (30 users)
└── smoke_test.py               # End-to-end automated test suite
```
---
## 🔧 Useful Commands
```bash
# View live logs from all services
docker compose logs -f orders payments cart products
# Rebuild a single service after code change
docker compose up -d --build orders
# Check all Prometheus targets
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep health
# Run smoke test
python smoke_test.py
# Stop everything (keeps data)
docker compose stop
# Full reset (deletes all data)
docker compose down -v
```
---
## 🧠 Concepts Demonstrated
| Concept | Implementation |
|---------|---------------|
| RED Method | Rate, Errors, Duration metrics on every endpoint |
| USE Method | Node Exporter (CPU utilization, saturation, errors) |
| Graceful Degradation | Services return `degraded` status when DB is unavailable |
| Structured Logging | JSON logs with level, service, message, timestamp |
| Distributed Tracing | OpenTelemetry spans across service boundaries |
| Log-Trace Correlation | Grafana: click log → jump to Tempo trace |
| Alert Fatigue Prevention | Severity levels, `for:` durations, inhibit rules |
| GitOps for Observability | All configs in code — datasources, dashboards, alert rules |
| Error Budget | Alert thresholds set based on SLO targets |
| Cardinality Control | Low-cardinality labels only (method, status, endpoint) |
---
## 📝 API Reference
### Orders Service `localhost:5001`
```
POST   /orders                    Create new order
GET    /orders                    List orders (paginated)
GET    /orders/:id                Get order
PATCH  /orders/:id/status         Update order status
GET    /health                    Health + DB status
GET    /metrics                   Prometheus metrics
```
### Payments Service `localhost:5002`
```
POST   /pay                       Process payment
GET    /payments/:txn_id          Get transaction
GET    /payments/stats            Revenue + success rate stats
GET    /health
GET    /metrics
```
### Products Service `localhost:5003`
```
GET    /products                  List all products
GET    /products?category=X       Filter by category
GET    /products/:id              Get product
POST   /products                  Create product (admin)
PATCH  /products/:id/stock        Update stock level
GET    /health
GET    /metrics
```
### Cart Service `localhost:5004`
```
GET    /cart/:user_id             View cart
POST   /cart/:user_id/add         Add item to cart
POST   /cart/:user_id/remove      Remove item from cart
POST   /cart/:user_id/checkout    Checkout → save to PostgreSQL
GET    /cart/history/:user_id     Checkout history (from DB)
GET    /cart/stats                Overall analytics
GET    /health
GET    /metrics
```
---
## 🤝 Contributing
Pull requests welcome. For major changes, open an issue first to discuss what you would like to change.
---
## 📄 License
MIT License — free to use for learning and portfolio purposes.
---
<div align="center">
<strong>Built to demonstrate production grade DevOps observability practices</strong><br>
<sub>Prometheus · Grafana · Loki · Tempo · OpenTelemetry · PostgreSQL · Docker</sub>
</div>