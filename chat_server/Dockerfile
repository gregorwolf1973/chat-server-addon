ARG BUILD_FROM
FROM ${BUILD_FROM}

# cryptography kommt als fertiges Alpine-Paket -> kein Rust-Build auf dem Pi
RUN apk add --no-cache \
      python3 \
      py3-pip \
      py3-cryptography \
      py3-requests

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Der Socket.IO-Client liegt unter app/static im Repo - kein Download beim
# Bauen, damit die Installation auf dem Pi nicht am CDN haengt.
COPY app /opt/chat

# Syntaxfehler sollen den Build brechen, nicht erst den Start auf dem Pi
RUN python3 -m compileall -q /opt/chat \
 && test -s /opt/chat/static/socket.io.min.js \
 && test -s /opt/chat/static/icon-192.png \
 && test -s /opt/chat/static/leaflet/leaflet.js \
 && test -s /opt/chat/static/weltkarte.svg

COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /opt/chat
CMD [ "/run.sh" ]
