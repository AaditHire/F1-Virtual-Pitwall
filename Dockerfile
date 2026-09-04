FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY knowledge ./knowledge
RUN python -m pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "f1_pitwall.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
