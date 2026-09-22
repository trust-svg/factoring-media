import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  formatRemaining,
  jstDayKey,
  isSameJstDay,
  formatJstTime,
  formatJstDayLabel,
  urgencyOf,
  isNearCap,
} from "./format";

// UTC 表記で書く(末尾 Z)。JST は +9h。
const at = (iso: string) => new Date(iso);

describe("jstDayKey", () => {
  it("JST の日付境界で切り替わる", () => {
    // 2026-08-24 14:59:59Z = JST 23:59:59 → まだ 8/24
    assert.equal(jstDayKey(at("2026-08-24T14:59:59Z")), "2026-08-24");
    // 2026-08-24 15:00:00Z = JST 翌 00:00:00 → 8/25
    assert.equal(jstDayKey(at("2026-08-24T15:00:00Z")), "2026-08-25");
  });

  it("UTC の日付境界では切り替わらない", () => {
    // UTC で日をまたぐが JST では同じ 8/25 の朝
    assert.equal(jstDayKey(at("2026-08-24T23:00:00Z")), "2026-08-25");
    assert.equal(jstDayKey(at("2026-08-25T01:00:00Z")), "2026-08-25");
  });

  it("月末・年末をまたいでも壊れない", () => {
    assert.equal(jstDayKey(at("2026-08-31T15:00:00Z")), "2026-09-01");
    assert.equal(jstDayKey(at("2026-12-31T15:00:00Z")), "2027-01-01");
  });

  it("isSameJstDay は同じ判定を使う", () => {
    assert.equal(
      isSameJstDay(at("2026-08-24T23:00:00Z"), at("2026-08-25T05:00:00Z")),
      true,
    );
    assert.equal(
      isSameJstDay(at("2026-08-24T14:00:00Z"), at("2026-08-24T16:00:00Z")),
      false,
    );
  });
});

describe("formatJstTime / formatJstDayLabel", () => {
  it("JST に変換して出す", () => {
    assert.equal(formatJstTime(at("2026-08-25T12:16:43Z")), "21:16:43");
    assert.equal(formatJstTime(at("2026-08-25T12:16:43Z"), false), "21:16");
  });

  it("曜日も JST 基準", () => {
    // 2026-08-25 は火曜
    assert.equal(formatJstDayLabel(at("2026-08-25T12:00:00Z")), "8/25(火)");
    // UTC では 8/24 だが JST では 8/25
    assert.equal(formatJstDayLabel(at("2026-08-24T15:30:00Z")), "8/25(火)");
  });
});

describe("formatRemaining", () => {
  it("1時間未満は MM:SS", () => {
    assert.equal(formatRemaining(8 * 60_000 + 47_000), "08:47");
    assert.equal(formatRemaining(59_000), "00:59");
  });

  it("1時間以上は HH:MM:SS", () => {
    assert.equal(formatRemaining(2 * 3_600_000 + 31 * 60_000 + 7_000), "02:31:07");
  });

  it("24時間以上は 日 + HH:MM", () => {
    assert.equal(formatRemaining(3 * 86_400_000 + 4 * 3_600_000 + 12 * 60_000), "3日 04:12");
  });

  it("0以下は終了", () => {
    assert.equal(formatRemaining(0), "終了");
    assert.equal(formatRemaining(-5000), "終了");
  });

  it("桁が揃う(同じ書式なら同じ長さ)", () => {
    assert.equal(formatRemaining(3_600_000).length, formatRemaining(36_000_000).length);
    assert.equal(formatRemaining(1000).length, formatRemaining(3_540_000).length);
  });
});

describe("urgencyOf", () => {
  const now = at("2026-08-25T12:00:00Z"); // JST 21:00

  it("残り10分以内は URGENT", () => {
    assert.equal(urgencyOf(at("2026-08-25T12:09:00Z"), now), "URGENT");
    assert.equal(urgencyOf(at("2026-08-25T12:10:00Z"), now), "URGENT");
  });

  it("同じ JST 日なら TODAY", () => {
    assert.equal(urgencyOf(at("2026-08-25T13:30:00Z"), now), "TODAY");
  });

  it("翌日以降は NORMAL", () => {
    assert.equal(urgencyOf(at("2026-08-26T11:00:00Z"), now), "NORMAL");
  });

  it("JST で日をまたいだ直後は NORMAL(UTC 基準にすると TODAY に化ける)", () => {
    const late = at("2026-08-25T14:50:00Z"); // JST 8/25 23:50
    const nextDay = at("2026-08-25T15:10:00Z"); // JST 8/26 00:10
    assert.equal(urgencyOf(nextDay, late), "NORMAL");
  });
});

describe("isNearCap", () => {
  it("8割以上で true", () => {
    assert.equal(isNearCap(8000, 10_000), true);
    assert.equal(isNearCap(7999, 10_000), false);
  });

  it("価格が未取得なら false(不明を警告に読み替えない)", () => {
    assert.equal(isNearCap(null, 10_000), false);
    assert.equal(isNearCap(undefined, 10_000), false);
  });

  it("上限が 0 以下でもゼロ除算しない", () => {
    assert.equal(isNearCap(100, 0), false);
    assert.equal(isNearCap(100, -1), false);
  });
});
