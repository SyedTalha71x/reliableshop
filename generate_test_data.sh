#!/bin/bash

echo "=== Generating test logs for Loki ==="

# Generate logs for different services
for service in cart orders payments products; do
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] INFO Test log from $service service" >> /var/log/containers/${service}-test.log
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] WARN Warning message from $service" >> /var/log/containers/${service}-test.log
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] ERROR Error condition in $service" >> /var/log/containers/${service}-test.log
done

# If you have the services running, generate some real logs
if command -v curl &> /dev/null; then
  echo "=== Making API calls to generate traces ==="
  for i in {1..5}; do
    curl -s http://localhost/api/cart > /dev/null 2>&1
    curl -s http://localhost/api/orders > /dev/null 2>&1
    curl -s http://localhost/api/payments > /dev/null 2>&1
    curl -s http://localhost/api/products > /dev/null 2>&1
    sleep 1
  done
fi

echo "=== Test data generated ==="