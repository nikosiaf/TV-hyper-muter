ARG BUILD_FROM=alpine:3.22
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-numpy py3-pillow tzdata

WORKDIR /app
COPY app/ /app/

# Run python directly, not under the base image's s6 /init: s6 starts CMD with a clean
# environment (no SUPERVISOR_TOKEN -> 401 from Core, no TZ -> UTC log times), and as PID 1
# python gets the Supervisor's SIGTERM itself, so main.py releases its mute on stop.
ENTRYPOINT [ "python3", "-u", "/app/main.py" ]
CMD []
