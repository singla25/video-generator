Feature: Docker build context (.dockerignore)
├── Scenario: build api/worker/web images
│   ├── ✅ Positive  — source, fonts, migrations, lockfiles, nginx.conf, env example stay in context
│   ├── ❌ Negative  — backend/spikes, nested node_modules/__pycache__, model weights, media, env files, .DS_Store are excluded
│   └── ⚠️ Edge      — every Dockerfile COPY source not ignored; tracked files kept <20 MB total, <5 MB each; comment explains "spikes"
└── Helper: dockerignore matcher (root-relative, `*`, `**`, `?`, `!`, last match wins, parent dir prefix) unit-tested first

Tests: tests/unit/meta/test_dockerignore_context.py (static, no Docker)
