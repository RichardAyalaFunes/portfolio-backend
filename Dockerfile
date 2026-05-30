FROM python:3.14-slim
WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-root --no-interaction

COPY src/ ./src/

ENV PYTHONPATH=/app/src

EXPOSE 8000
CMD ["uvicorn", "backend.infrastructure.main:app", "--host", "0.0.0.0", "--port", "8000"]
