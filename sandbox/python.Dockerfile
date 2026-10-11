# Run-stage image for Python sample agents. Install dependencies in a separate install step.
FROM python:3.11-slim-bookworm

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin agent
WORKDIR /work

# Run step: no package installs; agent code is mounted at /work
USER agent
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
