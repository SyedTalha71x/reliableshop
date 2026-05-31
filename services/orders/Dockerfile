FROM python:3.11-slim

WORKDIR /app

# Copy all services files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r orders/requirements.txt

EXPOSE 5001

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/health')"

CMD ["python", "orders/app.py"]