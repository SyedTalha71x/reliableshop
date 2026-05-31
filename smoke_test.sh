#!/bin/bash
set -e

BASE_ORDERS="http://localhost:5001"
BASE_PAYMENTS="http://localhost:5002"
BASE_PRODUCTS="http://localhost:5003"
BASE_CART="http://localhost:5004"

echo "=== Health Checks ==="
curl -s $BASE_ORDERS/health    | python3 -m json.tool
curl -s $BASE_PAYMENTS/health  | python3 -m json.tool
curl -s $BASE_PRODUCTS/health  | python3 -m json.tool
curl -s $BASE_CART/health      | python3 -m json.tool

echo ""
echo "=== Create Order ==="
curl -s -X POST $BASE_ORDERS/orders \
  -H "Content-Type: application/json" \
  -d '{"product_id":1,"qty":2}' | python3 -m json.tool

echo ""
echo "=== Process Payment ==="
curl -s -X POST $BASE_PAYMENTS/pay \
  -H "Content-Type: application/json" \
  -d '{"amount":79.99}' | python3 -m json.tool

echo ""
echo "=== Browse Products ==="
curl -s $BASE_PRODUCTS/products | python3 -m json.tool

echo ""
echo "=== Cart Flow ==="
curl -s -X POST $BASE_CART/cart/testuser/add \
  -H "Content-Type: application/json" \
  -d '{"product_id":2}' | python3 -m json.tool

curl -s -X POST $BASE_CART/cart/testuser/checkout | python3 -m json.tool

echo ""
echo "=== Metrics Exposed ==="
echo "Orders metrics lines:  $(curl -s $BASE_ORDERS/metrics   | wc -l)"
echo "Payments metrics lines: $(curl -s $BASE_PAYMENTS/metrics | wc -l)"
echo "Products metrics lines: $(curl -s $BASE_PRODUCTS/metrics | wc -l)"
echo "Cart metrics lines:    $(curl -s $BASE_CART/metrics     | wc -l)"

echo ""
echo "All services responding!"