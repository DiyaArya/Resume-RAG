# ── Frontend Dockerfile ─────────────────────────────────────────────────────────
# Stage 1: Build the Vite/React app
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source code and build for production
COPY . .
RUN npm run build

# Stage 2: Serve the built app with Nginx (tiny, fast web server)
FROM nginx:alpine

# Copy built files from the builder stage into Nginx's serve directory
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx config so /api/* requests are proxied to the backend
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80 (standard HTTP)
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
