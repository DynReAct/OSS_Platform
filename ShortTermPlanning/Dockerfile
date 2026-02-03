FROM python:3.12.3 AS builder
LABEL authors="Hector Flores"

# RUN pip install poetry==2.1.1

# Install system dependencies
RUN apt update && apt upgrade -y && \
    apt install -y  \
        bash \
        git \
        curl \
        make \
        cmake \
        gcc \
        g++ \
        musl-dev \
        python3-dev \
        libssl-dev \
        libsasl2-dev \
        zlib1g-dev \
        libzstd-dev \
        liblz4-dev

# Build librdkafka from source (latest version)
WORKDIR /tmp
RUN git config --global http.postBuffer 104857600 && \
    git clone --depth 1 --branch v2.8.0 https://github.com/confluentinc/librdkafka.git && \
    cd librdkafka && \
    ./configure --prefix=/usr --install-deps && \
    make -j$(nproc) && \
    make install && \
    cd .. && rm -rf librdkafka

WORKDIR /app

ENV PIP_REQUIRE_HASES=

ENV PIP_INDEX_URL=https://pypi.org/simple \
    PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org" \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

RUN pip install --upgrade pip wheel setuptools && \
    pip install --no-cache-dir "poetry==2.1.1" && \
    poetry --version

RUN poetry config installer.parallel false

COPY pyproject.toml ./

RUN for i in 1 2 3; do \
      poetry install --only main --no-root --no-interaction --no-ansi && break || \
      (echo "Poetry failed (attempt $i) — cleaning cache & retrying..." && rm -rf "$POETRY_CACHE_DIR" && sleep 5); \
    done

FROM python:3.12.3

ARG BUILD_DATE=""
ARG JENKINS_BUILD_ID=""

LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      es.upm.etsii.jenkins-pi.dynreact.build_id="${JENKINS_BUILD_ID}"

RUN apt update && apt upgrade -y && apt install -y gosu

WORKDIR /app

ARG DOCKER_REGISTRY=""

# Execute the command as 'appuser' and redirect logs to Docker logs
ENV PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PYTHONPATH="/app/shortterm" \
    IS_DOCKER="true" \
    LOCAL_REGISTRY=$DOCKER_REGISTRY \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Copy only the shared library from the builder stage
COPY --from=builder /usr/lib/lib* /usr/lib/

COPY dynreact/shortterm/common/ ./shortterm/dynreact/shortterm/common/
COPY dynreact/shortterm/agents/agent.py dynreact/shortterm/agents/equipment.py dynreact/shortterm/agents/log.py dynreact/shortterm/agents/material.py ./shortterm/dynreact/shortterm/agents/
COPY dynreact/shortterm/agents/__main__.py ./shortterm/
COPY dynreact/shortterm/shorttermtargets.py ./shortterm/dynreact/shortterm/
COPY dynreact/shortterm/timedelay.py ./shortterm/dynreact/shortterm/

RUN groupadd -r appgroup && useradd -r -u 1050 -g appgroup appuser
RUN groupadd docker
RUN usermod -aG docker appuser

COPY extras/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
