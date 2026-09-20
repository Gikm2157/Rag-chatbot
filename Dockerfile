FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" --upgrade pip
RUN pip install --no-cache-dir --no-deps --index-url "${TORCH_INDEX_URL}" torch==2.9.1+cpu
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" \
        filelock "typing-extensions>=4.10.0" "sympy>=1.13.3" \
        "networkx>=2.5.1" jinja2 "fsspec>=0.8.5" \
    && pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
