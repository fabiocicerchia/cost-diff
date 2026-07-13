# ponytail: optional — cost-diff installs fine via pipx/pip. This image just
# packages the CLI for environments that prefer containers. Runs as non-root.
FROM python:3.12-slim AS build
WORKDIR /src
COPY . .
RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.12-slim
RUN adduser --disabled-password --uid 10001 app
COPY --from=build /src/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
USER app
ENTRYPOINT ["cost-diff"]
