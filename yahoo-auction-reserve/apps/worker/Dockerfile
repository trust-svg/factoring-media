FROM mcr.microsoft.com/playwright:v1.49.0-noble

WORKDIR /app
COPY package.json package-lock.json* ./
COPY packages/db/package.json packages/db/
COPY packages/shared/package.json packages/shared/
COPY apps/worker/package.json apps/worker/
RUN npm ci --workspaces --include-workspace-root

COPY tsconfig.base.json ./
COPY packages ./packages
COPY apps/worker ./apps/worker
RUN npx prisma generate --schema packages/db/prisma/schema.prisma

CMD ["npm", "run", "start", "-w", "@yar/worker"]
