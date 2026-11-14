FROM node:22.23.3-alpine AS build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:1.30-alpine
COPY deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/nginx/forwarded-proto.conf.template /etc/nginx/templates/forwarded-proto.conf.template
COPY --from=build /web/dist /usr/share/nginx/html
ENV EI_BODY_MAX_MB=24
