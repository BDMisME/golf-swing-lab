import { describe, expect, it } from "vitest";
import {
  canvasClickToUprightNorm,
  catmullRomSubdivide,
  clamp01,
  computeOutputLayout,
  findFrameScopedNearestPoint,
  formatPtsUsToTimecode,
  projectUprightNormToOutputPx,
  scaleWidthAt1080,
  unprojectOutputPxToUprightNorm,
} from "../tracer/transforms";
import type { CanonicalTrackPoint, ExportAspectRatio } from "../tracer/types";

describe("Golf Tracer Studio R4 — Frontend Coordinate Space & Parity Math", () => {
  it("clamp01 clamps normalized coordinates strictly into [0, 1]", () => {
    expect(clamp01(-0.25)).toBe(0.0);
    expect(clamp01(0.42)).toBe(0.42);
    expect(clamp01(1.38)).toBe(1.0);
  });

  it("computeOutputLayout and projection roundtrip stay within <= 1e-6 across original / 16:9 / 9:16", () => {
    const aspects: ExportAspectRatio[] = ["original", "16:9", "9:16"];
    for (const aspect of aspects) {
      const layout = computeOutputLayout(1080, 1920, aspect);
      expect(layout.outputWidth % 2).toBe(0);
      expect(layout.outputHeight % 2).toBe(0);

      for (const [xn, yn] of [
        [0.12, 0.84],
        [0.5, 0.5],
        [0.88, 0.19],
      ]) {
        const [px, py] = projectUprightNormToOutputPx(xn, yn, layout);
        const [rxn, ryn] = unprojectOutputPxToUprightNorm(px, py, layout);
        expect(Math.abs(rxn - xn)).toBeLessThan(1e-6);
        expect(Math.abs(ryn - yn)).toBeLessThan(1e-6);

        // Verify integer pixel quantization delta <= 2.0 px (Preview/Export parity gate)
        const quantErr = Math.hypot(px - Math.round(px), py - Math.round(py));
        expect(quantErr).toBeLessThanOrEqual(2.0);
      }
    }
  });

  it("canvasClickToUprightNorm accounts for letterbox/pillarbox padding accurately", () => {
    // 1080x1920 portrait video inside a 1000x960 landscape container -> scale = 0.5, contentW = 540, padX = 230
    const [nx, ny] = canvasClickToUprightNorm(
      100 + 230 + 270, // center X of content
      50 + 480, // center Y of content
      100,
      50,
      1000,
      960,
      1080,
      1920
    );
    expect(Math.abs(nx - 0.5)).toBeLessThan(1e-4);
    expect(Math.abs(ny - 0.5)).toBeLessThan(1e-4);
  });

  it("scaleWidthAt1080 and catmullRomSubdivide and formatPtsUsToTimecode behave deterministically", () => {
    const layout1080 = computeOutputLayout(1080, 1920, "9:16");
    expect(scaleWidthAt1080(layout1080, 6)).toBe(6);

    const subdivided = catmullRomSubdivide(
      [
        [100, 800],
        [240, 520],
        [420, 280],
      ],
      6
    );
    expect(subdivided.length).toBe(13);
    expect(subdivided[0]).toEqual([100, 800]);
    expect(subdivided[subdivided.length - 1]).toEqual([420, 280]);

    expect(formatPtsUsToTimecode(1_250_000)).toBe("00:01.250");
    expect(formatPtsUsToTimecode(65_432_000)).toBe("01:05.432");
  });

  it("findFrameScopedNearestPoint restricts hit-testing to temporal window around currentPtsUs (P1-3)", () => {
    const makePt = (pts: number, x: number, y: number): CanonicalTrackPoint => ({
      track_id: "t1",
      track_type: "club_head",
      segment_id: "s1",
      source_video_id: "v1",
      source_pts_us: pts,
      source_frame_index: Math.round(pts / 16667),
      x_norm: x,
      y_norm: y,
      confidence: 0.9,
      uncertainty_px: 2.0,
      source_type: "manually_annotated",
      position_role: "manual_anchor",
      occlusion_state: "visible",
      phase: "downswing",
      raw_observation: null,
      created_by: "user",
      revision: 1,
    });

    // Two spatially overlapping points from backswing (300ms) and downswing (700ms)
    const points = [
      makePt(300_000, 0.50, 0.50),
      makePt(700_000, 0.502, 0.501),
    ];

    // At 700ms, only the 700_000 point should be selected even if click is slightly closer to 0.50, 0.50
    const hitAt700 = findFrameScopedNearestPoint(points, 0.50, 0.50, 705_000, 0.035, 45_000);
    expect(hitAt700).not.toBeNull();
    expect(hitAt700?.source_pts_us).toBe(700_000);

    // At 500ms (outside ±45ms of both points), clicking (0.50, 0.50) must return null so user doesn't drag wrong frame
    const hitAt500 = findFrameScopedNearestPoint(points, 0.50, 0.50, 500_000, 0.035, 45_000);
    expect(hitAt500).toBeNull();
  });
});

