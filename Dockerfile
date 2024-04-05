FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    npm \
    curl \
    software-properties-common \
    git \
    pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install python-dotenv

COPY app.py requirements.txt models.py  prompt_injection_utils.py /app/
COPY templates /app/templates

RUN pip3 install -r requirements.txt

EXPOSE 5000

ENTRYPOINT ["python", "app.py"]