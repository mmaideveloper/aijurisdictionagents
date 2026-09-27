FROM mcr.microsoft.com/playwright:v1.61.1-noble
WORKDIR /smoke
COPY laws-tests/deploy/package*.json ./
RUN --mount=type=secret,id=build_ca if [ -f /run/secrets/build_ca ]; then export npm_config_cafile=/run/secrets/build_ca; fi; npm ci
COPY laws-tests/deploy/smoke.mjs ./
CMD ["node", "smoke.mjs"]
