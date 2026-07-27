FROM python:3.12-slim AS base

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ src/
COPY dashboard.py .

# Create directories
RUN mkdir -p /app/inbox /app/data

EXPOSE 8888 8501

# Default: run the agent
CMD ["python", "-m", "src.main"]
