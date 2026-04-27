FROM node:20-alpine AS base
RUN apk add --no-cache openssl

FROM base AS deps
WORKDIR /app
COPY package.json ./
COPY prisma ./prisma/
RUN npm install --include=dev

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG DATABASE_URL
ENV DATABASE_URL=${DATABASE_URL}
RUN npx prisma generate
RUN npm run build

FROM base AS runner
RUN apk add --no-cache openssl
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/content ./content
COPY --from=builder /app/package.json ./package.json

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node_modules/.bin/next", "start"]
