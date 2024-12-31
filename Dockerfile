FROM python:3.11-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy project files
COPY pyproject.toml poetry.lock ./
COPY ocpp2twc/ ./ocpp2twc/
COPY README.md ./

# Configure Poetry
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

# Expose ports
EXPOSE 9000/tcp
EXPOSE 8080/tcp

# Run the application
CMD ["poetry", "run", "python", "-m", "ocpp2twc"]
