FROM node:24-alpine AS build
WORKDIR /web
COPY laws-tests/web/package*.json ./
RUN --mount=type=secret,id=build_ca if [ -f /run/secrets/build_ca ]; then export npm_config_cafile=/run/secrets/build_ca; fi; npm ci
COPY laws-tests/web/ ./
RUN npm run build
FROM nginx:stable-alpine
COPY laws-tests/deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist/ /usr/share/nginx/html/
