# Use an official lightweight Python image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy requirement list and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project so the static web/ files and dispatcher/ logic is present
COPY . .

# Expose port (Cloud Run defaults to 8080)
EXPOSE 8080

# Command to run FastAPI server on 0.0.0.0:8080
CMD ["uvicorn", "dispatcher.server:app", "--host", "0.0.0.0", "--port", "8080"]
