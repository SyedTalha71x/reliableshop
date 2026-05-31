FROM python:3.11-slim

WORKDIR /app

# Copy all shared services files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r cart/requirements.txt

EXPOSE 5004

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5004/health')"

CMD ["python", "cart/app.py"]