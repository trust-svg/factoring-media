// shared のラベル表(@yar/shared)と Prisma の enum がズレていないことの型レベル検査。
//
// shared は @yar/db に依存しない(worker/web の両方から使うため)ので、
// 突き合わせだけをここで行う。schema.prisma に enum 値を足してラベルを足し忘れると、
// **画面に生の enum 名が出る前にここで typecheck が落ちる**。
// 実行時には何もしない。
import type {
  ReservationStatus,
  AttemptOutcome,
  SessionStatus,
  AutoRaiseMode,
  ApprovalStatus,
} from "@yar/db";
import type {
  ReservationStatusKey,
  AttemptOutcomeKey,
  SessionStatusKey,
  AutoRaiseModeKey,
  ApprovalStatusKey,
} from "@yar/shared/labels";

// 双方向に代入できる = union として完全一致。片側でも欠けると never になり、
// 下の `: true` への代入が型エラーになる。
type Exact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;

const _reservationStatusMatches: Exact<ReservationStatus, ReservationStatusKey> = true;
const _attemptOutcomeMatches: Exact<AttemptOutcome, AttemptOutcomeKey> = true;
const _sessionStatusMatches: Exact<SessionStatus, SessionStatusKey> = true;
const _autoRaiseModeMatches: Exact<AutoRaiseMode, AutoRaiseModeKey> = true;
const _approvalStatusMatches: Exact<ApprovalStatus, ApprovalStatusKey> = true;

// 未使用変数の lint 対策(値としては何も意味を持たない)
export const LABEL_ENUM_CHECKS = [
  _reservationStatusMatches,
  _attemptOutcomeMatches,
  _sessionStatusMatches,
  _autoRaiseModeMatches,
  _approvalStatusMatches,
] as const;
