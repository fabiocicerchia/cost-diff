# ponytail: optional — cost-diff installs fine via pipx/pip. This image just
# packages the CLI for environments that prefer containers. Runs as non-root.
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS build
WORKDIR /src
COPY . .
# `pip wheel` drives the build backend directly, so the image needs no
# separately-installed (and separately-pinned) build frontend.
RUN pip wheel --no-cache-dir --no-deps -w dist .

FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
RUN adduser --disabled-password --uid 10001 app
COPY --from=build /src/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
USER app
# hardener: run this image with `docker run --read-only` for a read-only rootfs

# One-shot CLI tool, not a service — this just confirms the interpreter starts.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=1 \
    CMD ["python3", "-c", "import sys; sys.exit(0)"]

ENTRYPOINT ["cost-diff"]
