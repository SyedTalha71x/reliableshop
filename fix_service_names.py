#!/usr/bin/env python3
import re
import os

services = {
    'cart': 'cart-service',
    'orders': 'orders-service', 
    'payments': 'payments-service',
    'products': 'products-service'
}

for service, service_name in services.items():
    file_path = f'services/{service}/app.py'
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Check if Resource is already imported
    if 'from opentelemetry.sdk.resources import Resource' not in content:
        # Add import after opentelemetry imports
        content = content.replace(
            'from opentelemetry import trace',
            'from opentelemetry import trace\nfrom opentelemetry.sdk.resources import Resource'
        )
    
    # Replace TracerProvider creation
    old_provider = '''provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(
        endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317'),
        insecure=True
    )
))'''

    new_provider = f'''resource = Resource.create({{
    "service.name": "{service_name}",
    "service.namespace": "reliableshop",
    "deployment.environment": "production"
}})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(
        endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://tempo:4317'),
        insecure=True
    )
))'''
    
    if old_provider in content:
        content = content.replace(old_provider, new_provider)
        with open(file_path, 'w') as f:
            f.write(content)
        print(f"✅ Updated {service} service")
    else:
        print(f"⚠️ Could not find pattern in {service} service")

print("Done! Restart services to apply changes")
