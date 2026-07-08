# Nubra Beacon — frontend image (Next.js standalone).
# NOTE: rewrites (the /api/v1 same-origin proxy) are resolved from
# NEXT_PUBLIC_API_BASE at BUILD time and frozen into the standalone server,
# so the API target for the browser proxy is a build arg. Server-side fetches
# read API_BASE at runtime (set in docker-compose.yml).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_BASE=http://api:8400/api/v1
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN mkdir -p public && npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
