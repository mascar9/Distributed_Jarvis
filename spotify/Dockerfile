# Use Python 3.11 slim image as base
FROM python:3.13

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Copy requirements first (for better Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create a non-root user FIRST
RUN useradd --create-home --shell /bin/bash --uid 1000 app

# Create directories and set ownership
RUN mkdir -p /app/logs /app/data && \
    chown -R app:app /app

# Switch to app user (this should be a separate instruction)
USER app

# Expose the gRPC port
EXPOSE 50052

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50052'); channel.close()" || exit 1

# Run the gRPC server
CMD ["python", "service.py"]