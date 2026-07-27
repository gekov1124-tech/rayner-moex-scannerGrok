FROM python:3.12-slim

WORKDIR /app

# System deps for pandas / lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run scanner once and exit (perfect for Railway Cron)
CMD ["python", "main.py", "--universe", "sample", "--no-news"]
