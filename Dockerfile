FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY config.py .
COPY credentials.json ./credentials.json

# Volume mount for credentials.json - more secure than copying directly
VOLUME ["/app/credentials.json"]

CMD ["python", "main.py"]
