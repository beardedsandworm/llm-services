# llm-services

Deployable AI/agent runtime services for Wormlogic IX.

This repository contains the machinery. Private agent identity/history lives
separately in the local `golden-path` repository.

See:

- `docs/ARCHITECTURE.md`
- `docs/FIRST-LAUNCH.md`

Initial runtime:

- Hermes Agent in a derived Docker image
- OpenAI Codex as Leto's launch model
- Discord/text/voice groundwork
- local STT + TTS support
- OCR/document tooling
- dashboard/API groundwork
- optional local-inference Compose profile

No Caddy container runs here; Arrakis remains the reverse-proxy authority.
