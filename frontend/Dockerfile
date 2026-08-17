FROM node:22-alpine

WORKDIR /app

COPY package.json ./
COPY pnpm-lock.yaml ./

RUN corepack enable \
    && corepack prepare pnpm@10.24.0 --activate \
    && pnpm install --frozen-lockfile

COPY . .

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000').then(r => { if (!r.ok) process.exit(1) }).catch(() => process.exit(1))"]

CMD ["pnpm", "dev", "--hostname", "0.0.0.0"]
