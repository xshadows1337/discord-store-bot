FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ .

# Create directories that may be needed at runtime
# /data is the persistent volume mount point (set DATA_DIR=/data in Railway)
RUN mkdir -p delivered_orders products /data

# Default data directory — override with DATA_DIR=/data env var in Railway
ENV DATA_DIR=/data

# Run the bot
CMD ["python", "main.py"]
