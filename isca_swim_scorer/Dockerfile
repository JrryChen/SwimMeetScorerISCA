# Use Python 3.10 as the base image
FROM python:3.10

# Set working directory
WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
    
# Upgrade pip
RUN pip install --upgrade pip

# Copy requirements file
COPY ./requirements.txt /usr/src/app/requirements.txt
RUN pip install -r requirements.txt


# Copy the rest of the application
COPY . /usr/src/app/

# Install the local hytek-parser package
RUN pip install -e uploads/hytek-parser

CMD ["python", "manage.py", "migrate"] 

# Command to run the application
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"] 
