FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "web/app.py"]