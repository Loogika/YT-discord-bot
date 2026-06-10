# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS builder

ARG DENO_VERSION=2.3.7
ARG TARGETARCH

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv "${VIRTUAL_ENV}"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

RUN case "${TARGETARCH}" in \
        "amd64") deno_arch="x86_64-unknown-linux-gnu" ;; \
        "arm64") deno_arch="aarch64-unknown-linux-gnu" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl --fail --location --retry 3 \
        "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-${deno_arch}.zip" \
        --output /tmp/deno.zip \
    && unzip /tmp/deno.zip -d /tmp/deno \
    && install -m 0755 /tmp/deno/deno /usr/local/bin/deno


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 bot

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin/deno /usr/local/bin/deno

WORKDIR /app
COPY --chown=bot:bot bot.py .
COPY --chown=bot:bot loogika ./loogika

USER bot

RUN python -c "import discord, yt_dlp" \
    && python -m pip show yt-dlp-ejs >/dev/null \
    && yt-dlp --version \
    && ffmpeg -version >/dev/null \
    && deno --version

CMD ["python", "bot.py"]
