# IX LLM Services Architecture

## Repository boundary

`llm-services` owns deployable machinery:

- Dockerfiles
- Compose
- networks
- service mounts
- runtime bootstrap scripts
- health/operations documentation
- optional local inference services

`golden-path` owns private agent identity and institutional continuity:

- role/personality/backstory sources
- agent-owned SOUL files
- agent-owned skills
- job histories and handoffs
- private USER.md files (ignored by Git)

Hermes runtime state belongs under `/srv/ix/runtime/hermes`, not either repo.

## Host layout

```text
/srv/ix/
├── llm-services/          # shared/versioned deployment repo
├── golden-path/           # private local Git repo
├── runtime/
│   └── hermes/            # Hermes auth/config/sessions/logs/memory runtime
└── models/                # local model/cache storage
```

## Hermes and Golden Path

Hermes expects identity/memory at native paths under `HERMES_HOME`.

For Leto at launch:

```text
golden-path/agents/leto/SOUL.md
    -> /opt/data/SOUL.md

golden-path/agents/leto/skills/
    -> /opt/data/skills/

golden-path/agents/leto/USER.md
    -> /opt/data/memories/USER.md
```

The rest of `golden-path` is mounted at `/workspace/golden-path` so Leto can
read his role, personality source, historical briefing, job histories, and
handoff material.

The default Hermes profile is Leto for initial launch. Future specialists can
use Hermes named profiles under `/opt/data/profiles/<agent>/`; Hermes supports
multiple independently supervised gateways in a single container.

## Interaction surfaces

Initial:

- Discord: primary human conversation surface
- Hermes dashboard: administrative/debug/session surface
- Hermes API: LAN/VPN groundwork for future Kami/custom clients
- CLI/TUI: operator/debug use

Future:

- Kami voice endpoints
- Home Assistant integration
- additional agent profiles
- local inference backends

## Reverse proxy

Do not run Caddy on IX.

Arrakis remains the reverse-proxy authority. Add an Arrakis Caddy route to
IX:9119 after Hermes dashboard authentication is configured.

The Hermes API on 8642 should remain LAN/VPN-scoped initially.

## SSH hands

Hermes receives only Leto's dedicated operational SSH key plus SSH config and
known_hosts. IX's GitHub identity is deliberately not mounted.

Do not mount `/var/run/docker.sock` at launch. Host-Docker authority is a
separate privilege decision.

## Voice and document tooling

The derived Hermes image pre-installs:

- faster-whisper for local STT
- Edge TTS
- Discord voice dependencies
- ffmpeg / Opus
- Tesseract OCR
- OCRmyPDF
- Poppler
- firecrawl-anydoc
- PortAudio/espeak groundwork

This makes the capability available at launch even if we enable individual
features in stages.

## Local inference

The optional `ollama` Compose profile is scaffolding, not the initial Leto
model. Leto launches on the Hermes OpenAI Codex provider.

We can later replace or augment this service with llama.cpp, vLLM, or another
OpenAI-compatible endpoint without changing the core Hermes/golden-path split.
