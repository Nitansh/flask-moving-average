FROM python:3.11-slim

# Install system dependencies and certificate helpers
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Switch working directory
WORKDIR /app

# Upgrade pip and install pip-system-certs for secure connections
RUN pip install --upgrade pip && pip install pip-system-certs

# Copy the requirements file into the image
COPY ./requirements.txt /app/requirements.txt

# Install the dependencies (pip will now find the latest compatible versions)
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

# Copy every content from the local file to the image
COPY . /app

EXPOSE 5000
ENV PORT 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl --fail "http://localhost:5000/price_diff?symbol=ZYDUSLIFE&dma=DMA_20,DMA_50,DMA_100" || exit 1 

# Configure the container to run the Flask app
ENTRYPOINT [ "python" ]
CMD ["app.py" ]