FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./

# The optional `ca_bundle` build secret adds a CA bundle for builds behind a TLS-inspecting proxy.
RUN --mount=type=secret,id=ca_bundle \
    if [ -f /run/secrets/ca_bundle ]; then \
        export SSL_CERT_FILE=/run/secrets/ca_bundle PIP_CERT=/run/secrets/ca_bundle; \
    fi; \
    pip install --no-cache-dir uv==0.8.17 && uv sync --frozen --no-dev

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
