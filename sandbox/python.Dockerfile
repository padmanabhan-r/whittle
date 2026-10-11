# Sandbox image for Python agents. The install step writes the agent's
# dependencies into a volume mounted at /deps; the run step mounts that volume
# read-only and can reach only the proxy.
FROM python:3.11-slim-bookworm

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin agent \
    && mkdir -p /deps /work && chown agent:agent /deps /work
WORKDIR /work
USER agent
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/deps \
    HOME=/tmp
