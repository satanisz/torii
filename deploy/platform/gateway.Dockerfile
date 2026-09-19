FROM caddy:2@sha256:14a9c00d4e833ebc2b65d36515b37bde3b73f0b323a2663aaafc88953d8c4e3f
RUN setcap -r /usr/bin/caddy && mkdir -p /data /config && chown -R 10001:10001 /data /config
COPY Caddyfile /etc/caddy/Caddyfile
USER 10001:10001
EXPOSE 9443
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
