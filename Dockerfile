# Use an official Python runtime as a parent image
FROM python:3.11-slim

ARG VERSION=0.0.5

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the dependencies file to the working directory
COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the content of the local src directory to the working directory
COPY . .

# Run the application using Gunicorn
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app", "--bind", "0.0.0.0:5000"]