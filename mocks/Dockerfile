# One image for all mock backends; each compose service picks its app with `command`.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --root-user-action=ignore ".[mocks]"
COPY mocks mocks
