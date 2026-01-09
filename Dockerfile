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
COPY auth/ ./auth/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8004

# Expose port
EXPOSE 8004

# Run the application
CMD exec uvicorn client_management_api:app --host 0.0.0.0 --port ${PORT}

