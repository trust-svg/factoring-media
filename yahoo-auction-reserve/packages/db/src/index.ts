import { PrismaClient } from "@prisma/client";
import { loadLocalEnv } from "./loadEnv";

// ⚠️ new PrismaClient() より前。ここを通さないと、ホストで動かす
//    スクリプトが DATABASE_URL 未定義で落ちる(loadEnv.ts の経緯)。
loadLocalEnv();

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;

export * from "@prisma/client";
export { loadLocalEnv } from "./loadEnv";
