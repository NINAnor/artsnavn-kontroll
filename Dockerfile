FROM python:3.12

WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install -r requirements.txt

COPY src/static/matchdestination.png src/static/
COPY src/__init__.py src/webapp.py src/
COPY pyproject.toml .

CMD ["./src/webapp.py"]
