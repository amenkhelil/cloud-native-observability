FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY preprocessing.py evaluate.py detector.py ./
COPY data/ data/

RUN python evaluate.py --input data/windows.csv --model-output model.joblib

CMD ["python", "detector.py", "--prometheus-url", "http://prometheus:9090", "--model", "model.joblib", "--interval-seconds", "15"]
