FROM node:22-bookworm-slim AS base
# Prisma Client の実行に openssl が要る(スリムイメージには入っていない)
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# ---- deps: ロックファイル全体を検証するため全ワークスペースの package.json を置く ----
FROM base AS deps
COPY package.json package-lock.json ./
COPY packages/db/package.json packages/db/
COPY packages/shared/package.json packages/shared/
COPY apps/web/package.json apps/web/
COPY apps/worker/package.json apps/worker/
RUN npm ci

# ---- build ----
FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json tsconfig.base.json ./
COPY packages ./packages
COPY apps/web ./apps/web
# schema.prisma の binaryTargets は "native" を含む。ここで生成することで
# 実行イメージ(debian)向けのエンジンが選ばれる。
RUN npx prisma generate --schema packages/db/prisma/schema.prisma
# next build は静的解析のみで DB へ接続しないが、Prisma Client の初期化が
# 走るため DATABASE_URL の存在だけ満たしておく(値は使われない)。
ENV DATABASE_URL=postgresql://build:build@localhost:5432/build
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build -w @yar/web

# ---- run ----
FROM base AS runner
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/packages ./packages
COPY --from=build /app/apps/web ./apps/web
EXPOSE 3000
CMD ["npm", "run", "start", "-w", "@yar/web"]
