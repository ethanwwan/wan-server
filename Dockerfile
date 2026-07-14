FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Shanghai

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY server/input/ /app/server/input/
COPY server/output/ /app/server/output/
COPY . .

EXPOSE 8016

CMD ["python", "main.py"]
