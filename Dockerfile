FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ .

# Create directories that may be needed at runtime
RUN mkdir -p delivered_orders products

# Run the bot
CMD ["python", "main.py"]
