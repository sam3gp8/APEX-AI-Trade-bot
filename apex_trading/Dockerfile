ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

# Re-declare build args after FROM (required by Docker ARG scoping rules)
ARG BUILD_ARCH=amd64
ARG BUILD_VERSION=1.0.0

# Install Python and aiohttp via apk — avoids PEP 668 pip conflicts
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-aiohttp \
    py3-multidict \
    py3-yarl \
    py3-frozenlist \
    py3-aiosignal \
    curl \
    ca-certificates \
    tzdata

# aiofiles is not in Alpine apk repos — install with PEP 668 flag
RUN pip3 install --no-cache-dir --break-system-packages aiofiles==23.2.1

# Copy the rootfs overlay
COPY rootfs /

# Make the run script and server executable
RUN chmod a+x /opt/apex/run.sh /opt/apex/server.py

# Tell the HA Supervisor to run our script directly.
# We do NOT use ENTRYPOINT /init (s6-overlay) because the Supervisor
# launches the container with its own wrapper — s6 launched as a child
# process causes "can only run as pid 1". Using CMD with with-contenv
# is the correct pattern for single-process HA add-ons.
CMD [ "/opt/apex/run.sh" ]

LABEL \
    io.hass.name="APEX Trading AI" \
    io.hass.description="AI trading bot with Claude market analysis, live prices, and broker integration" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}"
