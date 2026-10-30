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
| Bubble geometry | DD-36: diameter 48/1080 of frame width, margin 12/1080 from the right and bottom edges (was 9 % / 3 % under DD-32); helpers `bubble_diameter(frame_width) -> int` and `bubble_box(frame_width, frame_height) -> (left, top, right, bottom)` in `vidgen.infrastructure.ffmpeg.label` |
| Look | DD-36: see-through faint black tint (alpha 40), white ring about 4 % of the diameter, white "AI" with a soft 1 px shadow; was an opaque dark disc (DD-32) |
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
│   ├── ✅ LS-R-P2 bubble box: diameter 48/1080 of width, 12/1080 margin right and bottom (DD-36)
│   ├── ✅ LS-R-P3 transparent everywhere outside the box; box corners alpha 0 (DD-36)
│   ├── ✅ LS-R-P4 white "AI" inside the ring, centred, height <= 0.6 d (DD-36)
│   ├── ✅ LS-R-P5 band renderer unchanged (size, opaque, dark)
│   ├── ❌ LS-R-N1 non-positive size -> ValueError, no file
│   ├── ❌ LS-R-N2 missing font -> DomainError INTERNAL_ERROR, no file
│   ├── ⚠️ LS-R-E1 odd, tiny, portrait and 4K frame sizes: box inside frame, no crash
│   ├── ⚠️ LS-R-E2 factory returns the renderer for the style; unknown style -> ValueError
│   └── ⚠️ LS-R-E3 bubble_diameter never below 1 and grows with width
├── Scenario: Bubble is composited by real ffmpeg  (tests/integration/ffmpeg/test_label_bubble_overlay.py)
│   ├── ✅ LS-C-P1 output width x height equal the template
│   ├── ✅ LS-C-P2 in every sampled frame (first, middle, last, in/after the extension) pixels differ from the template only inside the bottom-right box
│   ├── ✅ LS-C-P3 the bubble box differs from the template (mean abs diff >= 8) in every sampled frame (DD-36)
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

## DD-36 — see-through bubble look (task BB-RED)

Decision DD-36 (Admin chose design B): diameter 48/1080 of the width, margin 12/1080, faint black
tint (alpha 40), white ring about 4 % of the diameter, white "AI" with a 1 px soft shadow. The
band style and everything else stay as they were. Tests first; the developer implements exactly
these numbers.

```
Feature: see-through AI bubble (DD-36)
├── Scenario: Bubble geometry  (tests/unit/infra/test_bubble_renderer.py, test_bubble_look.py)
│   ├── ✅ LS-R-P2 box side and margins = round(w*48/1080), round(w*12/1080)   CHANGED
│   ├── ✅ LS-R-P6 worked examples 1080 -> 48/12, 320 -> 14/4, 1920 -> 85/21   NEW
│   ├── ✅ LS-R-P3 nothing drawn outside the box (exact, no slack)             CHANGED
│   └── ✅ LS-R-P3 box corners alpha 0 at every size                           CHANGED
├── Scenario: Bubble look inside the disc  (tests/unit/infra/test_bubble_look.py)
│   ├── ✅ LS-R-P7 body tint: alpha 30-50 at (cx, top + round(0.18 d)), RGB <= 20   NEW
│   ├── ✅ LS-R-P8 white ring 2 px at 1080: (cx, top), (cx, top+1) alpha >= 200, RGB >= 235   NEW
│   ├── ✅ LS-R-P9 outer edge anti-aliased (some alpha strictly between 1 and 254)  NEW
│   ├── ✅ LS-R-P4 >= 20 white "AI" pixels inside the ring, 4 px clear of it      REPLACES contrast test
│   ├── ✅ LS-R-P4 text bounding-box centre within 2 px of the circle centre      NEW
│   ├── ✅ LS-R-P4 text bounding-box height <= 0.6 d                              NEW
│   └── ✅ LS-R-P10 soft shadow: dark pixel (alpha >= 60, RGB <= 40) within 3 px of text  NEW
├── Scenario: Bubble composited by real ffmpeg  (tests/integration/ffmpeg/test_label_bubble_overlay.py)
│   ├── ✅ LS-C-P3 every sampled frame: mean abs diff inside the box >= 8 (PRESENT)   CHANGED (was dark probe < 70, diff > 20)
│   └── ✅ LS-C-E1 1080x1920: same rule inside the box                              CHANGED (was dark probe < 70)
└── Unchanged: LS-R-P1, LS-R-P5 band, LS-R-N1/N2, LS-R-E2/E3, LS-C-P1/P2/P4, LS-P-*, LS-L-*, LS-S-*
```

Old look assertions removed: diameter 9 % / margin 3 % (LS-R-P2 old form), opaque alpha 255 fill
(LS-R-P3 old form), light-on-dark contrast ratio >= 7 (LS-R-P4 old form), and the dark-probe
`pixel_mean < 70` checks in the ffmpeg tests (LS-C-P3, LS-C-E1).
