# Test tree: AI label style (DD-32, task LB-RED)

The AI label gets a style setting. `bubble` (new default) is a small rounded badge "AI" at the
bottom-right, drawn on top of the video, adding no height. `band` is today's behaviour (bilingual
band, at least 10 % of the height, top). Requirement C2 is intentionally relaxed for the bubble
(Admin decision, DD-32).

## Defaults chosen (recorded here, backend-dev implements exactly these names)

| Item | Choice |
|------|--------|
| Setting | `Settings.label_style: Literal["bubble", "band"] = "bubble"`, env `VIDGEN_LABEL_STYLE`; anything else rejected (no silent fallback), like `ai_backend` |
| Render config | `RenderConfig.label_style: str = "bubble"`; an unknown value raises `ValueError`; `render_config(settings)` copies it |
| Bubble geometry | diameter about 9 % of frame width, margin about 3 % of width from the right and bottom edges; helpers `bubble_diameter(frame_width) -> int` and `bubble_box(frame_width, frame_height) -> (left, top, right, bottom)` in `vidgen.infrastructure.ffmpeg.label` |
| Look | opaque dark fill (same dark as the band), light text "AI", on every frame |
| Renderer | `PillowBubbleRenderer(latin_font: Path, text: str = "AI")` next to `PillowLabelRenderer`, same `render_label(width, height, out)` port. Contract: writes a transparent RGBA PNG of exactly `width x height` (the frame size) with the bubble drawn at `bubble_box`. So the encoder keeps overlaying at 0:0 and needs no change. |
| Factory | `build_label_renderer(style, devanagari_font, latin_font)` in the same module: band gives `PillowLabelRenderer`, bubble gives `PillowBubbleRenderer`, unknown raises `ValueError` |
| Pipeline | `RowRenderer`: bubble calls `labels.render_label(template.width, template.height, out)` and never calls `band_height`; band unchanged `(width, band_height(...))`; `label_band_share` ignored for bubble |
| Local AI | `local_label_band_height(settings, frame_h)` returns 0 for bubble, unchanged (at least 10 %) for band |
| Quality | a bubble video is not failed for a missing band (checker never looks for a band) |

Existing tests that relied on the default being a band now say `label_style="band"` explicitly:
`tests/integration/worker/test_render_row.py` (2 tests), `tests/e2e/conftest.py`,
`tests/unit/ai_local/test_label_height.py`. Until the field exists these fail with a TypeError
(RenderConfig) and nothing else changes.

```
Feature: AI label style (bubble | band)
├── Scenario: Admin configures the style  (tests/unit/infra/test_label_style_setting.py)
│   ├── ✅ LS-S-P1 default is bubble (env var unset)
│   ├── ✅ LS-S-P2 accepts bubble and band
│   ├── ✅ LS-S-P3 VIDGEN_LABEL_STYLE overrides the default
│   ├── ❌ LS-S-N1 rejects "", "BAND", " band", "bar", "none", "stripe"
│   └── ⚠️ LS-S-E1 label_band_share still validated (>= 0.10) when style is bubble
├── Scenario: Bubble PNG is rendered  (tests/unit/infra/test_bubble_renderer.py)
│   ├── ✅ LS-R-P1 PNG is exactly the frame size, RGBA
│   ├── ✅ LS-R-P2 bubble box: diameter ~9 % of width, ~3 % margin right and bottom, inside the frame
│   ├── ✅ LS-R-P3 non-empty: opaque dark fill, transparent outside the circle and outside the box
│   ├── ✅ LS-R-P4 text legible: light "AI" pixels centred in the bubble, contrast ratio >= 7
│   ├── ✅ LS-R-P5 band renderer unchanged (size, opaque, dark)
│   ├── ❌ LS-R-N1 non-positive size -> ValueError, no file
│   ├── ❌ LS-R-N2 missing font -> DomainError INTERNAL_ERROR, no file
│   ├── ⚠️ LS-R-E1 odd, tiny, portrait and 4K frame sizes: box inside frame, no crash
│   ├── ⚠️ LS-R-E2 factory returns the renderer for the style; unknown style -> ValueError
│   └── ⚠️ LS-R-E3 bubble_diameter never below 1 and grows with width
├── Scenario: Bubble is composited by real ffmpeg  (tests/integration/ffmpeg/test_label_bubble_overlay.py)
│   ├── ✅ LS-C-P1 output width x height equal the template
│   ├── ✅ LS-C-P2 in every sampled frame (first, middle, last, in/after the extension) pixels differ from the template only inside the bottom-right box
│   ├── ✅ LS-C-P3 the bubble is present (dark, covers the picture) in every sampled frame
│   ├── ✅ LS-C-P4 band style still adds the 10 % band at the top, size unchanged
│   └── ⚠️ LS-C-E1 production size 1080x1920: size unchanged, bubble in the corner
├── Scenario: Pipeline picks the renderer by style  (tests/integration/worker/test_render_row_label_style.py, tests/unit/worker/test_runner_label_style.py)
│   ├── ✅ LS-P-P1 default config: label requested at the full template size (320x240)
│   ├── ✅ LS-P-P2 band config: label requested at (320, 24) as before
│   ├── ✅ LS-P-P3 render_config(settings) copies label_style (default bubble, band)
│   ├── ✅ LS-P-P4 band_height is not called for bubble
│   ├── ✅ LS-P-P5 the quality check still runs and a bubble row completes
│   ├── ❌ LS-P-N1 RenderConfig(label_style="stripe") -> ValueError
│   └── ⚠️ LS-P-E1 label_band_share (0.2) is ignored for bubble, honoured for band
├── Scenario: Local AI path honours the style  (tests/unit/ai_local/test_label_style_local.py, test_label_height.py)
│   ├── ✅ LS-L-P1 local_label_band_height is 0 for bubble (default)
│   ├── ✅ LS-L-P2 band: at least 10 % of the frame (existing guard, now explicit band)
│   └── ⚠️ LS-L-E1 band share above 10 % is honoured, bubble ignores it
└── Scenario: Quality checks and bubble  (same pipeline file)
    ├── ✅ LS-Q-P1 FakeQualityChecker passes a bubble output
    └── ⚠️ LS-Q-E1 a checker failure still fails the row for bubble (OUTPUT_CHECK_FAILED)
```

Requirement mapping: C2 (relaxed, DD-32) is covered by LS-R-*, LS-C-*, LS-P-*; "adds no height"
by LS-C-P1/E1; "default bubble, band kept" by LS-S-*, LS-P-P1/P2, LS-L-*.
