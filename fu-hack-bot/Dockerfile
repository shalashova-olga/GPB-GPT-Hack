FROM python:3.10.15-slim-bullseye

WORKDIR /app

COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge && \
    rm requirements.txt

COPY ./src/ ./src/

WORKDIR /app/src

ENTRYPOINT ["python", "-u", "tg-app.py"]