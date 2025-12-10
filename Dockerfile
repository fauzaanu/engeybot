FROM python:3.13-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY main.py .

# Install dependencies
RUN uv sync --no-dev

# Expose port for webhook
EXPOSE 8080

# Run the bot
CMD ["uv", "run", "main.py"]
