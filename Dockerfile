# Herohackathon - Flat Structure Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything into /app (Flat structure)
COPY . .

# Cloud Run defaults to PORT 8080
EXPOSE 8080

# Run main.py using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
