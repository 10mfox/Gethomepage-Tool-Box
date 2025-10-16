# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set build-time arguments
ARG VERSION=dev

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV VERSION=${VERSION}

# Set the working directory in the container
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY . .

# Command to run the application using Gunicorn
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]