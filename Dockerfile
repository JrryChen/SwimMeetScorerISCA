# Use Python 3.10 as the base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Install the local hytek-parser package
RUN pip install -e isca_swim_scorer/uploads/hytek-parser

# Command to run the application
CMD ["python", "isca_swim_scorer/manage.py", "runserver", "0.0.0.0:8000"] 