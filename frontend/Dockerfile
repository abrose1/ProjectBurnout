# Pin Node 23 so Vite 8 always runs on a supported runtime (avoids Nixpacks defaulting to Node 18).
# Railway: set service Root Directory to `frontend` and ensure VITE_API_URL is available at build time.

FROM node:23-bookworm-slim AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM node:23-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN npm install -g serve@14
COPY --from=builder /app/dist ./dist

# Railway injects PORT at runtime
CMD ["sh", "-c", "exec serve -s dist -l tcp://0.0.0.0:${PORT}"]
