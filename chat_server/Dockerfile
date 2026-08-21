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

COPY app /opt/chat

# Socket.IO-Client lokal ausliefern (kein CDN zur Laufzeit noetig)
RUN wget -q -O /opt/chat/static/socket.io.min.js \
      https://cdn.socket.io/4.7.5/socket.io.min.js

COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /opt/chat
CMD [ "/run.sh" ]
