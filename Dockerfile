FROM python:3.12-slim

WORKDIR /build

RUN apt-get update && \
    apt-get install -y zip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lambda_function.py .

RUN zip lambda_package.zip lambda_function.py && \
    cd /usr/local/lib/python3.12/site-packages && \
    zip -ur /build/lambda_package.zip . -x "**/__pycache__/*" "**/*.pyc"