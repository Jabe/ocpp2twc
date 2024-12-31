FROM python:3.11-slim

WORKDIR /app

# Install Poetry using binary distribution
RUN pip install --only-binary :all: poetry

# Copy project files
COPY pyproject.toml poetry.lock ./
COPY ocpp2twc/ ./ocpp2twc/
COPY README.md ./

# Configure Poetry and install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi \
    && pip uninstall -y poetry

# Expose ports
EXPOSE 9000/tcp
EXPOSE 8080/tcp

# Run the application directly with python
CMD ["python", "-m", "ocpp2twc"]
