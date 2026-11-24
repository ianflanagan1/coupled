# COUPLED:node-version: docker
FROM node:24.11.1-alpine AS web
WORKDIR /web
COPY web/ .

FROM python:3.13-slim
COPY app/ /app/
COPY --from=web /web/dist /app/static
CMD ["python", "-m", "app"]
