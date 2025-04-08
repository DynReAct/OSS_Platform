FROM python:3.12.3 AS builder
LABEL authors="Hector Flores"

RUN pip install poetry==2.1.1

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

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
RUN git clone --depth 1 --branch v2.8.0 https://github.com/confluentinc/librdkafka.git && \
    cd librdkafka && \
    ./configure --prefix=/usr --install-deps && \
    make -j$(nproc) && \
    make install && \
    cd .. && rm -rf librdkafka

WORKDIR /app

COPY pyproject.toml ./

RUN poetry install --only main --no-root --no-interaction && rm -rf $POETRY_CACHE_DIR

FROM python:3.12.3

RUN apt update && apt upgrade -y && apt install -y gosu

WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv \
    PYTHONPATH="/app/shortterm" \
    IS_DOCKER="true" \
    PATH="/app/.venv/bin:$PATH"


COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Copy only the shared library from the builder stage
COPY --from=builder /usr/lib/lib* /usr/lib/

COPY dynreact/shortterm/shared/common/ ./shortterm/common/
COPY dynreact/shortterm/agents/ dynreact/shortterm/config.cnf ./shortterm/

RUN groupadd -r appgroup && useradd -r -u 1050 -g appgroup appuser
RUN groupadd docker
RUN usermod -aG docker appuser  # Replace 'myuser' with your container user

COPY extras/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
