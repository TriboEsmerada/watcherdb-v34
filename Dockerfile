# ============================================================================
# WatcherDB Dockerfile
# Multi-stage build for production-ready container
# ============================================================================

# ----------------------------------------------------------------------------
# Stage 1: Builder
# ----------------------------------------------------------------------------
FROM python:3.11-slim as builder

LABEL maintainer="WatcherDB Team <support@watcherdb.io>"
LABEL description="SQL Server monitoring and diagnostics platform"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Driver for SQL Server
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# ----------------------------------------------------------------------------
# Stage 2: Runtime
# ----------------------------------------------------------------------------
FROM python:3.11-slim

# Copy ODBC drivers from builder
COPY --from=builder /opt/microsoft /opt/microsoft
COPY --from=builder /etc/apt/sources.list.d/mssql-release.list /etc/apt/sources.list.d/

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create app user (non-root for security)
RUN groupadd -r watcherdb && useradd -r -g watcherdb watcherdb

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=watcherdb:watcherdb . /app/

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/reports && \
    chown -R watcherdb:watcherdb /app/data /app/logs /app/reports

# Switch to non-root user
USER watcherdb

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Default command
CMD ["uvicorn", "watcherdb_main:app", "--host", "0.0.0.0", "--port", "8000"]
