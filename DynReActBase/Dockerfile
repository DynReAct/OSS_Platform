FROM python:3.12
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
COPY pyproject.toml README.md ./
COPY dynreact dynreact
CMD pip wheel . --no-cache-dir --disable-pip-version-check --no-deps --wheel-dir dist
