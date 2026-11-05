# The app's bundle for the ediarum.platform: dist/embed.js + dist/assets/,
# served by nginx at the root (the platform's proxy maps /apps/index/ here).
#
#   docker build -t ediarum-index-frontend frontend/

FROM node:24-alpine AS build
WORKDIR /app

# install deps first, against the lockfile, for layer caching
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
      npm ci --no-audit --no-fund --prefer-offline

# type-check + vite build -> /app/dist; fail if the contract exports went missing
COPY . .
RUN npm run build && npm run check-embed

# ---- serve stage ----
FROM nginx:1.27-alpine AS serve
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
