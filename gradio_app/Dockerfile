FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /home/user/app

COPY --chown=user:user requirements.txt /home/user/app/requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt \
        "uvicorn[standard]>=0.46" "websockets>=10.4"

COPY --chown=user:user app.py /home/user/app/app.py
COPY --chown=user:user gradio_app /home/user/app/gradio_app

EXPOSE 7860

CMD ["python", "app.py"]
