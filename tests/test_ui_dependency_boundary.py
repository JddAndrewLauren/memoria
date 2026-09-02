"""The dependency boundary rule #24's acceptance criteria asks for:
"nothing under `ui/` may import a package capable of reaching a model API".

There is no model client anywhere in this repo today, so a behavioural test
would assert nothing - this is the mechanism the issue names instead: a
denylist over `ui/package.json`'s declared dependencies, checked here rather
than left as a doc comment, so it fails the day someone `npm install`s an
SDK that can reach a model, which is the day it matters.
"""

import json
from pathlib import Path

PACKAGE_JSON = Path(__file__).resolve().parent.parent / "ui" / "package.json"

# Package names, and scopes/prefixes, whose whole reason to exist is
# reaching a hosted or local model API. Not exhaustive by construction - a
# denylist never is - but it is the mechanism, not the list, that the
# acceptance criterion asks for: a new entry is one line to add the day a
# real offender shows up.
DENYLIST_EXACT = {
    "openai",
    "anthropic",
    "@anthropic-ai/sdk",
    "@anthropic-ai/bedrock-sdk",
    "@anthropic-ai/vertex-sdk",
    "cohere-ai",
    "replicate",
    "groq-sdk",
    "mistralai",
    "@mistralai/mistralai",
    "together-ai",
    "ollama",
    "ai",  # the Vercel AI SDK - a model-calling client, despite the generic name
    "langchain",
    "llamaindex",
    "@huggingface/inference",
    "@google/generative-ai",
    "@google/genai",
    "@azure/openai",
}
DENYLIST_PREFIXES = (
    "@anthropic-ai/",
    "@langchain/",
    "@google-cloud/vertexai",
    "@google/generative-ai",
    "@aws-sdk/client-bedrock",
)


def test_ui_declares_no_dependency_capable_of_reaching_a_model_api():
    manifest = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    declared = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}

    violations = sorted(
        name
        for name in declared
        if name in DENYLIST_EXACT or any(name.startswith(prefix) for prefix in DENYLIST_PREFIXES)
    )
    assert not violations, (
        f"ui/package.json declares a package that can reach a model API: {violations} - "
        "the view layer may never call a model directly (docs/adr/0002-ui-is-a-react-client.md)"
    )
