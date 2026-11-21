"""Names shared by the Modal client and the Modal app source (stdlib only, no imports).

``backend/modal_app/app.py`` and ``modal_client.py`` both import these, so the deployed
function names and the names the client looks up cannot drift apart.
"""

from __future__ import annotations

DEFAULT_APP_NAME = "vidgen-ai"
FN_TRANSCRIBE = "transcribe"
FN_HAS_SAMPLE = "has_sample"
FN_UPLOAD_SAMPLE = "upload_sample"
FN_SYNTHESIZE = "synthesize"
