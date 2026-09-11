FROM public.ecr.aws/docker/library/python:3.11-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application and configuration reader
COPY app.py .
COPY config_reader.py .

# Copy configuration file
COPY config/config.conf config/config.conf

# Set OpenTelemetry environment variables for observability
# Required for agents hosted outside of AgentCore runtime
# Note: These will be overridden by ECS task definition with values from config.conf
ENV AGENT_OBSERVABILITY_ENABLED=true
ENV OTEL_PYTHON_DISTRO=aws_distro
ENV OTEL_PYTHON_CONFIGURATOR=aws_configurator
ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
ENV OTEL_TRACES_EXPORTER=otlp
# Service name and log groups will be set by ECS task definition from config.conf
ENV OTEL_RESOURCE_ATTRIBUTES=service.name=max-training-agent
ENV OTEL_EXPORTER_OTLP_LOGS_HEADERS=x-aws-metric-namespace=bedrock-agentcore

# Expose port
EXPOSE 8080

# Run with ADOT instrumentation (same as other agents)
CMD ["opentelemetry-instrument", "python", "-u", "app.py"]
