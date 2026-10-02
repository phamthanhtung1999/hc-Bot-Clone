FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken

WORKDIR /app

COPY requirements.txt .
# Bake the tokenizer into the image so runs never download it.
RUN pip install -r requirements.txt \
 && python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

COPY kbsync ./kbsync
COPY main.py ask.py ./

RUN useradd --create-home app && chown -R app /app
USER app

# `docker run IMAGE` and `docker run IMAGE main.py` both run one sync and exit.
ENTRYPOINT ["python"]
CMD ["main.py"]
