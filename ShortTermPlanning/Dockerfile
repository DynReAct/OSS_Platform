FROM python:3.12.3 AS builder
LABEL authors="Hector Flores"

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

# Opciones de pip limpias, sin rastro de poetry
ENV PIP_INDEX_URL=https://pypi.org/simple \
    PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org" \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Copiamos el requirements.txt
COPY requirements.txt ./

# Creamos el entorno virtual, actualizamos pip/setuptools 
# e instalamos requirements con --no-build-isolation para que flatdict instale bien
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --upgrade pip wheel setuptools && \
    /app/.venv/bin/pip install --no-build-isolation -r requirements.txt


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

# IMPORTANTE: Copiamos la carpeta entera para que __main__.py quede en su sitio correcto
COPY dynreact/shortterm/agents/ ./shortterm/dynreact/shortterm/agents/

COPY dynreact/shortterm/shorttermtargets.py ./shortterm/dynreact/shortterm/
COPY dynreact/shortterm/timedelay.py ./shortterm/dynreact/shortterm/

RUN groupadd -r appgroup && useradd -r -u 1050 -g appgroup appuser
RUN groupadd docker
RUN usermod -aG docker appuser

COPY extras/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
