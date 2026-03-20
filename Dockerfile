FROM python:3.11-slim

# mono-complete needed only if you compile .exe on server
# Comment out to speed up deploy (source-only mode still works)
RUN apt-get update && apt-get install -y \
    mono-complete \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use shell form so $PORT is expanded from Render.com environment variable
CMD sh -c "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --worker-class eventlet --timeout 120 server:app"
