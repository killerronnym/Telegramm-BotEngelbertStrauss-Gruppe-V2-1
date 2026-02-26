FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP web_dashboard.app
ENV PORT 9002

# Set work directory
WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Ensure scripts are executable
RUN chmod +x docker-entrypoint.sh

# Ensure instance and logs directories exist
RUN mkdir -p /app/instance /app/logs

# Expose port
EXPOSE 9002

# Run the application via entrypoint
ENTRYPOINT ["./docker-entrypoint.sh"]
