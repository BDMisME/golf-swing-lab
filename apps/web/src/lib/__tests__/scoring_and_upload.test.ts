import { describe, expect, it } from "vitest";
import {
  computeChunkPlan,
  formatCoverageStatus,
  formatMsToTimestamp,
} from "../api";

describe("Golf Swing Lab 前端核心工具與誠實評分門檻測試", () => {
  it("formatMsToTimestamp 正確轉換毫秒為分秒毫秒字串", () => {
    expect(formatMsToTimestamp(0)).toBe("00:00.0");
    expect(formatMsToTimestamp(1500)).toBe("00:01.5");
    expect(formatMsToTimestamp(65432)).toBe("01:05.4");
  });

  it("computeChunkPlan 確保最小分段不低於 5MB 並涵蓋完整檔案大小", () => {
    const totalBytes = 19 * 1024 * 1024;
    const chunks = computeChunkPlan(totalBytes, 8 * 1024 * 1024);
    expect(chunks.length).toBe(3);
    expect(chunks[0].partNumber).toBe(1);
    expect(chunks[0].start).toBe(0);
    expect(chunks[2].end).toBe(totalBytes);
  });

  it("formatCoverageStatus 於指標覆蓋率 < 70% 時誠實顯示資料不足 (N/A)", () => {
    const low = formatCoverageStatus(null, 0.45);
    expect(low.isInsufficient).toBe(true);
    expect(low.displayScore).toContain("資料不足");
    expect(low.badgeText).toContain("45%");

    const valid = formatCoverageStatus(89.4, 1.0);
    expect(valid.isInsufficient).toBe(false);
    expect(valid.displayScore).toBe("89.4");
    expect(valid.badgeText).toContain("100%");
  });
});
