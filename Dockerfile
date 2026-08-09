FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    postgresql-client \
    git \
    libgl1 \
    libglib2.0-0 \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*


# Add a build argument to control installation of identity packages
ARG INSTALL_IDENTITY=true

# Copy files necessary for dependency installation to leverage Docker cache
COPY pyproject.toml requirements.txt /app/

# Create a dummy app package folder so that pip install -e . can run successfully
RUN mkdir -p /app/app && touch /app/app/__init__.py

# Install base and dev dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -e ".[dev]"

# Optionally install identity dependencies (heavy AI/ML packages)
RUN if [ "$INSTALL_IDENTITY" = "true" ] ; then \
      apt-get update && apt-get install -y --no-install-recommends \
      g++ \
      python3-dev \
      libgl1 \
      libglib2.0-0 \
      && ldconfig \
      && rm -rf /var/lib/apt/lists/* \
      && pip install --no-cache-dir -e ".[identity]" ; \
    fi

# Copy the rest of the application code
COPY . /app

# Ensure entrypoint script is executable
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
