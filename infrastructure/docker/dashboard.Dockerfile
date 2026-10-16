# Same application container model locally and on the future Linux coordinator.
FROM node:24.22.0-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 GODFATHER_CONTAINER_BUILD=1
COPY package.json package-lock.json ./
COPY apps/dashboard/package.json ./apps/dashboard/package.json
RUN npm ci
COPY apps/dashboard ./apps/dashboard
RUN npm run build

FROM node:24.22.0-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build --chown=node:node /app/apps/dashboard/.next/standalone ./
COPY --from=build --chown=node:node /app/apps/dashboard/.next/static ./apps/dashboard/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/dashboard/server.js"]
