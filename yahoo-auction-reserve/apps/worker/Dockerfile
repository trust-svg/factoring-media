# Playwright のブラウザ実体はイメージ側に同梱されている。npm の playwright と
# イメージタグがズレると「ブラウザが見つからない」で入札実行時にだけ落ちる
# (= 最悪のタイミングでの故障)。apps/worker/package.json の playwright は
# exact pin し、この ARG と必ず一致させること。
ARG PLAYWRIGHT_VERSION=1.62.1
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble

WORKDIR /app

# npm ci はロックファイル全体(=全ワークスペース)の整合性を検証するため、
# worker が使わない apps/web の package.json も置く必要がある。
COPY package.json package-lock.json ./
COPY packages/db/package.json packages/db/
COPY packages/shared/package.json packages/shared/
COPY apps/web/package.json apps/web/
COPY apps/worker/package.json apps/worker/
RUN npm ci

COPY tsconfig.base.json ./
COPY packages ./packages
COPY apps/worker ./apps/worker
RUN npx prisma generate --schema packages/db/prisma/schema.prisma

ENV NODE_ENV=production
CMD ["npm", "run", "start", "-w", "@yar/worker"]
