# ---- build the React PWA ----
FROM node:20-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/yarn.lock* ./
RUN yarn install --network-timeout 1000000
COPY frontend/ .
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
RUN yarn build

# ---- serve static + reverse-proxy /api + auto HTTPS ----
FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/build /srv
