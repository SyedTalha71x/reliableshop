FROM python:3.11-slim

WORKDIR /app

# Copy all shared services files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r products/requirements.txt

EXPOSE 5003

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5003/health')"

CMD ["python", "products/app.py"]