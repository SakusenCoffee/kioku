# Kioku server mode (docs/server.md): the app page, and the collection kept
# on the server. Built by tools/docker.sh from build/dist (tools/dist.sh),
# with Anki's core for the server from PyPI at the app's version.
FROM python:3.13-slim
ARG ANKI_PY_VERSION
RUN test -n "$ANKI_PY_VERSION" && pip install --no-cache-dir "anki==$ANKI_PY_VERSION"
WORKDIR /kioku
COPY tools/serve.py tools/
COPY server/ server/
COPY build/dist/ site/
RUN useradd --uid 1000 --create-home kioku && mkdir /data && chown kioku /data
USER kioku
ENV KIOKU_DATA=/data KIOKU_HOST=0.0.0.0 KIOKU_PORT=8080 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8080
CMD ["sh", "-c", "exec python tools/serve.py site \"$KIOKU_PORT\""]
