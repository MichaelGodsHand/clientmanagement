FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY client_management_api.py .
COPY client_manager.py .

# Copy auth module (required for /auth/exchange endpoint)
COPY auth/ ./auth/

# Set environment variables
ENV PYTHONUNBUFFERED=1
# Cloud Run sets PORT=8080 by default, but we'll use it from environment
ENV PORT=8080

# Expose port (Cloud Run uses 8080 by default)
EXPOSE 8080

# Run the application
# Cloud Run sets PORT environment variable (defaults to 8080)
# Use sh -c to properly expand environment variable
CMD ["sh", "-c", "uvicorn client_management_api:app --host 0.0.0.0 --port ${PORT:-8080}"]

