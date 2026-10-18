---
name: test-tree
description: Template and checklist for writing a feature's test case tree (positive, negative and edge cases) in docs/test-tree/<feature>.md before any test code is written. Use when the tester starts a feature or the CEO outlines tests in a plan.
---

# Test case tree

Save as `docs/test-tree/<feature-slug>.md`. Every acceptance criterion (AC) maps to at least one case.

## Template

```markdown
# Test tree — <Feature name>
Plan: docs/plans/<feature>.md

## Scenario 1: <user action, e.g. "Generate video from text + images">
| ID | Type | Given / When | Then | AC | Test file::name |
|----|------|--------------|------|----|-----------------|
| S1-P1 | ✅ Positive | 3 valid images + 20-word script | MP4 1080p, duration ±0.1 s of audio | AC1 | tests/unit/test_render.py::test_renders_mp4_from_images |
| S1-N1 | ❌ Negative | image is a renamed .txt file | 422 "unsupported image", no job created | AC3 | ... |
| S1-E1 | ⚠️ Edge | 1 image, 1-character script | valid ≥1 s video | AC1 | ... |
```

## Edge-case checklist for the video generator
Pick every one that applies; write "N/A — reason" for the rest.

**Input:** empty input · single item · max count · max file size +1 byte · zero-length / 1-frame video · max duration · odd or tiny resolution (1×1, 7×5) · huge resolution (8K) · portrait / landscape / square · missing audio · silent audio · mismatched audio and video length · corrupt / truncated file · wrong extension vs real format · unsupported codec · variable frame rate

**Text & names:** empty text · very long text · unicode, emoji, RTL (Arabic/Hebrew), Hindi/Devanagari · special characters and spaces in filenames · path-traversal names (`../../x.mp4`) · prompt-injection text in user content

**System:** duplicate job submission (idempotency) · concurrent jobs · worker crash mid-render then retry · timeout · storage full or unavailable · queue down · temp files cleaned after failure · cancellation mid-job

## Rules
- Negative tests assert a **clear error message** and **no partial output file**.
- Use small synthetic fixtures (generated in `conftest.py`), never real personal media.
- Mark tests over ~2 s as `@pytest.mark.slow`.
