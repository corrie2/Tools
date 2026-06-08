from __future__ import annotations

import json
import sys

from agent_long_memory.embeddings import _embed_texts_in_process


def main() -> None:
    payload = json.loads(sys.stdin.read())
    vectors = _embed_texts_in_process(
        list(payload["texts"]),
        model_name=str(payload["model_name"]),
    )
    sys.stdout.write(json.dumps(vectors))


if __name__ == "__main__":
    main()
