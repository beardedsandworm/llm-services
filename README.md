# 🤖 llm-services

> Deployable, recoverable, and observable AI/agent runtime services for **IX**.

---

## 💡 Philosophy

> **Agent infrastructure should be reproducible without making agent identity, private history, or mutable runtime state part of the deployment repository.**

`llm-services` is the AI and agent runtime deployment layer for **IX** (`server02`).

It owns:

* 🤖 **Hermes Agent runtime**
* 🧠 **LLM and model-service integration**
* 🐳 **Docker Compose deployment**
* 🔐 **SOPS-encrypted service secrets**
* 🧩 **Versioned runtime configuration**
* ⚙️ **Repo-owned deployment automation**
* 🔊 **Speech and audio tooling**
* 👁️ **OCR and document tooling**
* 🌐 **Internal DNS monitoring**
* 📊 **Container/image monitoring**
* 🔑 **Repository-specific GitHub authentication**
* 🖥️ **Homepage Docker visibility**

It deliberately does **not** own private agent identity or history.

That state lives separately in the local-only:

```text
golden-path
```

repository.

---

## ⚡ Mental Model

```text
Host ready
    ↓
Recover secrets
    ↓
Prepare runtime
    ↓
Build Hermes
    ↓
Start services
    ↓
Install monitoring
    ↓
Attach private agent state
    ↓
Observe continuously
```

Operationally:

```text
Define → Decrypt → Prepare → Deploy → Attach → Observe → Recover
```

* **Define** → Compose and runtime configuration
* **Decrypt** → SOPS-encrypted service secrets
* **Prepare** → runtime directories, prompts and local state links
* **Deploy** → build and start the agent services
* **Attach** → connect private Golden Path state
* **Observe** → DNS, container and image monitoring
* **Recover** → rebuild IX without putting private agent identity in GitHub

---

# 🖥️ Host

`llm-services` runs on:

| Host | ID | OS | Role |
| --- | --- | --- | --- |
| 🧠 IX | `server02` | Ubuntu | LLM / agent runtime host |

Current IX hardware:

```text
CPU:     Intel Core i7-11700
RAM:     64 GB
GPU:     8 GB VRAM
Storage: 1 TB NVMe
```

Host bootstrap, packages, machine identity, SSH credentials, age identity, WireGuard and system configuration are owned by:

```text
linux-environments
```

`llm-services` begins where the IX host bootstrap ends.

---

# 🧩 Repository Structure

```text
llm-services/
├── compose.yaml
├── deploy.sh
├── dc
│
├── config/
│   └── ...
│
├── env/
│   └── server02.env
│
├── scripts/
│   ├── decrypt-secrets.sh
│   ├── bootstrap-runtime.sh
│   └── ...
│
├── services/
│   └── internal-dns-monitor/
│
├── secrets/
│   └── server02/
│       └── *.enc
│
├── runtime/
│   └── server02/
│       ├── secrets/
│       └── ...
│
├── systemd/
│   ├── llm-services-image-check.service
│   ├── llm-services-image-check.timer
│   └── ...
│
└── docs/
    ├── ARCHITECTURE.md
    └── FIRST-LAUNCH.md
```

The exact runtime structure may evolve as additional agents and model backends are introduced.

Generated runtime state is not Git authority.

---

# 🧱 Repository Boundary

## ✅ Versioned Here

`llm-services` owns the machinery required to run the IX agent environment.

That includes:

* Compose definitions
* Hermes image/build configuration
* runtime bootstrap logic
* model/backend configuration intended for version control
* internal DNS monitor integration
* monitoring systemd units
* deployment scripts
* SOPS-encrypted service secrets
* non-secret environment metadata
* infrastructure documentation

---

## 🔒 Private Agent State Lives Elsewhere

The local-only:

```text
golden-path
```

repository owns private agent identity and long-lived behavioral state.

That includes material such as:

* agent personalities
* agent-specific instructions
* agent skills
* private context/history
* evolving agent identity files
* reviewable self-edits

Golden Path is intentionally:

```text
local only
```

It is **not** pushed to GitHub.

It should not be copied wholesale into `llm-services`, committed here, or treated as infrastructure configuration.

---

## 🗄️ Mutable Runtime State

Git also does not own transient application state such as:

* generated caches
* model caches
* application logs
* temporary documents
* speech/OCR working files
* runtime sessions
* generated agent state
* downloaded models
* other locally produced artifacts

Those require their own recovery or regeneration policy.

---

# 🤖 Agent Architecture

IX is designed as an agent host rather than a single-chatbot appliance.

Current and planned Wormlogic agents include:

| Agent | Role |
| --- | --- |
| 🏜️ **Leto** | Primary general-purpose Wormlogic agent |
| 🧭 **Moneo** | Orchestration / coordination |
| 🛡️ **Duncan** | Security-focused agent |
| 🩺 **Yueh** | Health / system-health role |
| 🧠 **Thufir** | Kubernetes / job-oriented role |

Additional personalities may be introduced over time without requiring the infrastructure repository to own their private identity.

---

# 🧠 Hermes

Hermes is the primary agent harness on IX.

`llm-services` builds a derived Hermes image locally rather than depending entirely on a registry-hosted custom image.

The deployment flow includes:

```bash
./dc build hermes
```

before reconciling the stack.

The resulting runtime provides the common execution environment for Wormlogic agents.

---

## Model Strategy

The architecture is intended to support multiple model sizes and backends.

Conceptually:

```text
agent request
     ↓
Hermes
     ↓
model selection
     ↓
local or remote inference
```

The runtime may use:

* hosted model APIs
* local models
* task-specific model sizes
* different resident/cached models depending on workload

Local inference remains optional rather than a hard dependency for every agent.

---

# 🏜️ Leto

Leto is the primary interactive Wormlogic agent.

The infrastructure repository provides Leto's runtime.

Leto's identity does **not** live here.

Conceptually:

```text
llm-services
     ↓
Hermes runtime
     ↓
Leto process
     ↑
Golden Path
identity / skills / context
```

This separation allows the runtime to be destroyed and rebuilt without treating Leto's private identity as disposable container state.

---

# 🗂️ Golden Path

Golden Path is a separate, local-only repository.

Its purpose is to preserve and version agent identity independently of infrastructure.

The intended recovery model is:

```text
llm-services
    ↓
rebuild runtime

golden-path
    ↓
restore identity
```

The two repositories solve different problems.

`llm-services` answers:

> **How do the agents run?**

Golden Path answers:

> **Who are the agents?**

They should remain separate.

---

# 🔐 Secrets

Encrypted service secrets live under:

```text
secrets/server02/
```

using:

```text
SOPS + IX's age identity
```

IX's age identity itself belongs to the machine recovery process in `linux-environments`.

---

## Runtime Secrets

Encrypted sources are materialized under:

```text
runtime/server02/secrets/
```

using:

```bash
./scripts/decrypt-secrets.sh
```

Runtime plaintext must never be committed.

Standalone runtime components should consume the centrally materialized secret rather than inventing their own encryption/decryption workflow.

---

# 🏗️ Runtime Bootstrap

IX requires some runtime structure that should exist independently of individual container lifetimes.

That reconciliation is owned by:

```text
scripts/bootstrap-runtime.sh
```

The script prepares the expected runtime environment and can safely be rerun.

It may create or reconcile:

* runtime directories
* expected file structure
* baseline prompt/state files
* symlinks into local agent state
* other non-secret runtime prerequisites

The deployment script invokes this before building or starting Hermes.

---

# 🔑 Repository Deploy Key

IX uses a repository-specific GitHub deploy key:

```text
~/.ssh/id_ed25519_git_llm-services
```

Example key comment:

```text
server02:github:llm-services
```

The Git repository is locally bound to that key through:

```text
core.sshCommand
```

This keeps `llm-services` authentication independent from:

* the normal IX SSH identity
* `linux-environments`
* other Wormlogic repositories

The normal scheduled credential capture in `linux-environments` can discover and preserve the deploy key afterward.

---

# 🚀 Deployment

The primary deployment entry point is:

```bash
./deploy.sh
```

Current deployment flow:

```text
validate repository
        ↓
decrypt secrets
        ↓
bootstrap runtime
        ↓
build Hermes
        ↓
./dc up -d
        ↓
install internal DNS monitor
        ↓
install image-check timer
        ↓
create / verify llm-services deploy key
        ↓
bind Git repository to deploy key
        ↓
display public deploy key
        ↓
Press Enter to continue
```

The deployment script owns the IX application layer.

Host preparation remains the responsibility of `linux-environments`.

---

# 🔄 Recovery Flow

The intended IX recovery path is:

```text
clone linux-environments
        ↓
bootstrap IX
        ↓
recover age / SSH / WireGuard
        ↓
reboot
        ↓
clone llm-services
        ↓
restore / clone local Golden Path
        ↓
./deploy.sh
        ↓
register deploy key if new
        ↓
capture credentials
        ↓
agents return
```

Golden Path restoration is part of IX recovery, but its content remains outside the public service repository.

---

# 🌐 Networking and Reverse Proxy

IX does **not** run its own Caddy container.

That is intentional.

Reverse-proxy authority remains on:

```text
Arrakis
```

through the `docker-services` Caddy deployment.

The network model is:

```text
client
   ↓
Arrakis / Caddy
   ↓
LAN
   ↓
IX service
```

Because IX and Arrakis live on the same local network, inter-host service traffic should normally use the LAN rather than WireGuard addresses.

WireGuard remains available for remote-network use and recovery, not as the default service transport between neighboring hosts.

---

# 🖥️ Homepage Integration

IX runs:

```text
homepage-docker-proxy
```

to expose limited Docker metadata to the central Homepage deployment.

Homepage itself remains on Arrakis.

Conceptually:

```text
Homepage on Arrakis
        ↓
homepage-docker-proxy
        ↓
IX Docker Engine
```

This allows the Wormlogic dashboard to show IX service/container state without exposing the full Docker socket directly.

---

# 🌐 Internal DNS Monitoring

IX includes a repo-owned internal DNS monitor under:

```text
services/internal-dns-monitor/
```

The installer reconciles its runtime integration and associated systemd automation.

The monitor validates the internal DNS path from IX's perspective rather than assuming that DNS works merely because the local resolver responds.

This gives the monitoring system another independent observation point inside the home network.

---

# 🔊 Speech and Audio

The runtime is designed to support local speech capabilities.

This includes groundwork for:

* 🎙️ speech-to-text
* 🔊 text-to-speech
* 🗣️ voice interaction
* 💬 text-based agent interfaces

Speech tooling is treated as shared agent infrastructure rather than something each agent must independently implement.

---

# 👁️ OCR and Document Tooling

IX also provides local tooling for agent workflows involving:

* OCR
* PDFs
* images
* documents
* structured extraction

This allows agent workflows to process local materials without making every task depend on an external document-processing service.

---

# 💬 Agent Interfaces

Hermes is intended to support multiple chat surfaces over time.

Potential/current integration work includes:

* Discord
* Matrix
* Telegram
* other text interfaces
* voice interfaces

Transport is separate from identity:

```text
Discord / Matrix / Telegram
            ↓
          Hermes
            ↓
           Agent
            ↑
       Golden Path
```

Changing the chat transport should not redefine the agent.

---

# 🧪 Local Inference

Local inference is supported as an optional deployment path rather than a mandatory component of the base stack.

Conceptually:

```text
./dc up -d
```

provides the normal runtime.

Additional model-serving components can be introduced through an optional Compose profile when local inference is desired.

This keeps the base recovery path smaller while preserving a route toward increasingly local operation.

---

# 🛠️ `dc` Wrapper

Use the repository wrapper for Compose lifecycle operations:

```bash
./dc config
./dc config --services
./dc ps
./dc logs
./dc pull
./dc build
./dc up -d
./dc down
```

Examples:

```bash
./dc logs hermes
./dc restart hermes
./dc up -d --force-recreate hermes
```

Remember:

```text
restart ≠ recreate
```

A restart does not apply changed:

* environment variables
* bind mounts
* Compose configuration
* image definitions

Use:

```bash
./dc up -d
```

or:

```bash
./dc up -d --force-recreate <service>
```

when the container definition changes.

---

# 📊 Monitoring

`llm-services` owns monitoring for the IX application layer.

Current monitoring includes:

```text
llm-services-image-check.service
llm-services-image-check.timer
```

and the internal DNS monitoring service.

Monitoring should answer questions such as:

```text
Is Hermes running?
Can IX resolve internal services?
Are runtime dependencies available?
Are images stale?
Did something meaningful change?
```

---

# 🔔 Monitoring Philosophy

The same Wormlogic policy applies here:

> **Silence is success.**

Healthy steady-state operation should not generate unnecessary noise.

Notifications should represent:

* agent-runtime failures
* container failures
* DNS failures
* image updates
* deployment failures
* meaningful state changes
* other actionable conditions

---

# 🧪 Verification

## Repository

```bash
git status --short --branch
```

---

## Compose

```bash
./dc config
./dc config --services
./dc ps
```

Include stopped services when needed:

```bash
./dc ps --all
```

---

## Hermes

```bash
./dc logs --tail=100 hermes
```

---

## Runtime Secrets

List filenames without exposing their contents:

```bash
find runtime/server02/secrets \
  -maxdepth 1 \
  -type f \
  -printf '%f\n' \
  | sort
```

---

## Monitoring

```bash
systemctl status \
  internal-dns-monitor.timer \
  llm-services-image-check.timer
```

---

## Docker Proxy

```bash
./dc ps homepage-docker-proxy
```

---

# 🧱 Recovery Boundary

A complete IX recovery depends on four distinct layers:

```text
1. linux-environments
   ↓
host + machine credentials + networking

2. llm-services
   ↓
agent runtime + deployment machinery

3. golden-path
   ↓
private agent identity + history

4. mutable/runtime recovery
   ↓
models + caches + other state worth preserving
```

None of these replaces the others.

---

# 🧠 Design Rules

A few rules keep IX sane:

* **Host configuration belongs in `linux-environments`.**
* **Agent runtime infrastructure belongs here.**
* **Private agent identity belongs in Golden Path.**
* **Golden Path remains local-only.**
* **Secrets are encrypted with SOPS at rest.**
* **Decrypted service secrets live only in runtime state.**
* **Each repository gets its own GitHub deploy key.**
* **Deployment scripts should be safe to rerun.**
* **Runtime preparation should be explicit and reproducible.**
* **Arrakis remains reverse-proxy authority.**
* **LAN traffic is preferred for normal Arrakis ↔ IX service communication.**
* **Containers are disposable; identity is not.**
* **Generated runtime state does not become accidental Git structure.**
* **Monitoring should report actionable change rather than routine success.**
* **Recovery paths are infrastructure and should be tested like infrastructure.**

---

# 🗺️ Repository Ownership

The Wormlogic infrastructure repositories have distinct jobs:

| Repository | Responsibility |
| --- | --- |
| 🧠 `linux-environments` | Host bootstrap, credentials, networking and host automation |
| 🐳 `docker-services` | Arrakis application stack |
| 🤖 `llm-services` | IX agent and LLM runtime |
| 🚀 `vps-services` | Heighliner application and public-edge stack |
| 🪱 `wormlogic-gitops` | Shai-Hulud Talos / Flux / Kubernetes state |
| 🧬 `golden-path` | Local-only agent identity and skills |

The infrastructure boundary is:

```text
linux-environments
        ↓
prepare IX

llm-services
        ↓
deploy runtime

golden-path
        ↓
attach identity
```

Each layer owns one problem.

---

# 📚 Documentation

More detailed agent/runtime documentation lives under:

```text
docs/
```

Important starting points:

* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
* [`docs/FIRST-LAUNCH.md`](docs/FIRST-LAUNCH.md)

The README describes the repository boundary and recovery model.

The documents under `docs/` should carry the deeper implementation detail.

---

# 🔭 Future Direction

The long-term objective is not simply to run one agent.

It is to make IX a durable, recoverable agent platform.

The desired failure/recovery path is:

```text
IX dies
   ↓
rebuild host
   ↓
recover credentials
   ↓
deploy llm-services
   ↓
restore Golden Path
   ↓
restore / reacquire models
   ↓
agents return
```

Future work can add:

* more specialized agents
* more local inference
* improved model routing
* Matrix-based chat
* richer voice interaction
* additional monitoring
* Kubernetes job integration
* better persistent-state backup

without changing the ownership model.

---

# 📌 Summary

`llm-services` is the deployable AI and agent-runtime layer for IX.

It provides:

* 🤖 Hermes-based agent execution
* 🧠 local and remote model integration
* 🐳 Compose-managed runtime services
* 🔐 SOPS-encrypted service secrets
* 🔑 repository-specific GitHub authentication
* 🏗️ reproducible runtime preparation
* 🌐 internal DNS monitoring
* 🖥️ centralized Homepage visibility
* 🔊 speech and audio tooling
* 👁️ OCR/document tooling
* 📊 image/runtime monitoring
* 🧬 clean separation from private Golden Path identity
* 🔄 a repeatable recovery path

The goal is simple:

> **IX should be rebuildable without rebuilding the agents from scratch.**

---

## 🧑‍💻 Author

Matthew J Garry
