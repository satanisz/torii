FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
WORKDIR /work/apps/web
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
COPY --from=contracts . /work/specs/0001-project-object-version/contracts
RUN npm run build
FROM caddy:2@sha256:14a9c00d4e833ebc2b65d36515b37bde3b73f0b323a2663aaafc88953d8c4e3f
RUN setcap -r /usr/bin/caddy
COPY --from=platform web.Caddyfile /etc/caddy/Caddyfile
COPY --from=build /work/apps/web/dist /srv
USER 10001:10001
EXPOSE 8080
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
