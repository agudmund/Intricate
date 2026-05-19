# AWS Integration

This laptop runs Intricate. Intricate is a spatial canvas for thought, an always-on-top whisper-volume companion to a writing-and-plushies machine. It does not — and should not — host the kind of compute a 1.2B-parameter feed-forward 3D reconstruction model demands. When the canvas needs that scale of work done, it asks a *workshop* to do it, and the workshop is somewhere else entirely.

This document describes that workshop, the first time it is being built. The trigger is HY-World 2.0 — a Tencent multi-modal 3D world model that wants an NVIDIA A10G or larger and a CUDA toolchain we have no business installing on a Lenovo Yoga Slim 6. But the design here is not for HY-World. HY-World is the first citizen of a generalisable cloud layer that future heavy workloads — image diffusion, flux, the panorama half of HY-World itself, the world expansion model, whatever else lands on the desktop — will all enter through.

## Session mission

> *"At the end of this session, HY-World is installed on an AWS machine Aevar can log into."*

Everything beyond that — the FastAPI server, the Intricate-side `EC2Node`, the bearer-token auth between local and remote, the spot-interruption handling — lives in the **Beyond this session** list at the bottom. This session establishes the link and proves a heavy citizen can live on it. The rest is the next several sessions of this multi-day arc.

## What stays local, what goes remote

Intricate keeps doing what it already does on this laptop. The Intel Iris Xe is more than enough for the canvas, the nodes, the live theme reload. Nothing about the spatial workflow needs the cloud.

What lives remote is the heavy *transient* work — model loads, inference passes, output rendering. Artifacts come back as files (`.ply`, `.mp4`, depth maps, normal maps) that drop into the local session like any other ImageNode-grade asset. The cloud is invoked when needed, dormant otherwise. Contextual absence applies: if AWS credentials are missing or the workshop is not provisioned, the relevant cloud-bound nodes simply don't surface. No error banners, no disabled-state stubs, just nothing. Same gating discipline as everywhere else.

## Identity model

Identities are split by *what they are*, not by *who is driving them*. This is the part Aevar specifically asked for guidance on; the recommendation below is the one we proceed with unless flagged.

| Identity | Type | Used by | Notes |
|---|---|---|---|
| **Root account** | AWS root | (no one, after setup) | MFA-protected, credentials locked away. Used only for the initial IAM setup, never again. |
| **`penelope`** | IAM user | Aevar (human) | MFA on console login, access keys for CLI. Lives in `~/.aws/credentials` on this laptop. Scoped policies — not full admin. |
| **`intricate-runtime`** | IAM role | Intricate (the app, at runtime) | Assumed via STS from `penelope`. Narrow policy: `ec2:Start*`, `ec2:Stop*`, `ec2:Describe*` on tagged instances only, plus scoped S3 read/write. No long-lived keys inside the app. |
| **`ec2-hyworld-instance`** | IAM role | The EC2 instance itself | Attached as instance profile. Lets the box pull model weights from S3 / a future Intricate bucket without keys on disk. |

### Claude's place in this

Claude (this assistant) does not get a separate IAM user. The candid reason: Claude has no AWS identity of its own to sign with. When Claude calls AWS during a chat session, the call goes out *as `penelope`* — but through the AWS MCP Server's local proxy, which signs the request with `penelope`'s credentials via IAM SigV4. The principal is honestly `penelope`; the *medium* is the MCP proxy.

CloudTrail captures both, which gives the audit trail three clean categories:

| Principal | Source / User-Agent | Means |
|---|---|---|
| `penelope` | AWS CLI or console | Aevar in console or CLI directly |
| `penelope` | `mcp-proxy-for-aws/...` | Claude acting on Aevar's behalf through MCP |
| `intricate-runtime` *(assumed role)* | `boto3/...` (or successor) | The Intricate app at runtime |

This is the cleaner answer than a fake identity, and it falls out of the AWS MCP Server's design naturally — the proxy's user-agent string is what distinguishes Claude-in-chat from manual Aevar use, no per-call tag plumbing needed.

### Connector path — AWS MCP Server

Aevar's instinct that a pre-built bridge exists was correct. The first design pass missed it; a second look, prompted by the *Claude Platform on AWS* / Bedrock April-2026 announcements, surfaced the real connector. **There are two distinct AWS-on-Claude threads, and only one of them is ours:**

| Thread | What it is | Relevance |
|---|---|---|
| **Claude Platform on AWS** *(Coming Soon, April 2026)* | Use Claude *through* AWS — Anthropic's native platform with AWS IAM credentials, consolidated billing, CloudTrail. *Consumer side.* | Not our path. We're not trying to access Claude from AWS; we're trying to access AWS from Claude. |
| **AWS MCP Server** *(generally available)* | An MCP server Claude talks to as a client. The server proxies AWS API calls using IAM SigV4 auth. *Tool side.* | **This is the connector.** |

The AWS MCP Server is hosted by AWS at `https://aws-mcp.us-east-1.api.aws/mcp`. Authentication uses a small open-source local proxy — `mcp-proxy-for-aws` — that bridges MCP's OAuth-2.1 expectations to IAM SigV4. The proxy runs locally, picks up credentials from `~/.aws/credentials` like every other AWS tool, and forwards signed requests to the AWS-hosted MCP endpoint. The server exposes four tools:

| Tool | Purpose |
|---|---|
| `call_aws` | Execute any of 15,000+ AWS API operations under the calling identity's permissions |
| `search_documentation` | Search current AWS docs at query time |
| `read_documentation` | Fetch up-to-date AWS reference pages |
| `run_script` | Run Python in a sandbox that inherits IAM perms but has no network access |

Registered on this laptop with:

```bash
claude mcp add-json aws-mcp --scope user \
  '{"command":"uvx","args":["mcp-proxy-for-aws@latest","https://aws-mcp.us-east-1.api.aws/mcp","--metadata","AWS_REGION=us-east-1"]}'
```

Prerequisite was `uv` (Astral's Python launcher), installed via the official PowerShell installer to `~/.local/bin/`. The server initially shows "Failed to connect" in `claude mcp list` — that is expected until the `penelope` IAM credentials are configured locally; the proxy has nothing to sign with yet.

## Region, instance, storage, budget

| Decision | Choice | Reasoning |
|---|---|---|
| **Region** | `us-east-1` | Stability, biggest pool, lowest pricing. Latency is irrelevant — Aevar confirmed AWS's transatlantic loop routes everything through Denmark regardless, so European-region instances aren't actually closer for our workload. |
| **Instance** | `g5.xlarge` (NVIDIA A10G, 24 GB VRAM) | Natural fit for HY-World 2.0's 1.2B parameters with BF16. Headroom for model + activations + future panorama / world-expansion citizens. |
| **Pricing** | Spot, on-demand fallback | ~$0.30/hr spot vs ~$1.00/hr on-demand. Jobs are short, interruption-tolerant. Start with on-demand for the first session to keep variables low; switch to spot once stop/restart is solid. |
| **Storage** | Detached EBS volume, ~50 GB gp3 | Model weights (~5 GB), example data, output artifacts. Persistent across instance stop/start so we never re-download. Attached via instance profile, not baked into AMI. |
| **AMI** | Deep Learning AMI, Ubuntu 22.04, CUDA 12.4 | Avoids hand-installing CUDA toolkit + cuDNN. PyTorch 2.4.0 still installs cleanly from the wheel index. |
| **Budget ceiling** | **$25/month hard alert** | Set in AWS Budgets *before* any provisioning. Aevar's prior render-farm-scale work was billed pro-bono by Amazon; Intricate has no such pre-allocation. The ceiling is the rail. |

## The two bridges

AWS gets called from this project in two distinct contexts, with different needs and different machinery. Conflating them is the easy mistake; keeping them separate is the design.

### Bridge 1 — Claude (in chat) → AWS

When Claude is helping in a chat session — building this integration, debugging an EC2 issue, querying a budget — Claude reaches AWS through the **AWS MCP Server** described above. Claude is an MCP client; the AWS MCP Server is the bridge. Local plumbing is the `mcp-proxy-for-aws` invoked via `uvx`, configured at user scope so it's available across all Aevar's Claude Code projects.

This bridge inherits `penelope`'s permissions and is bounded by them. Claude cannot exceed what Aevar can do, and CloudTrail will record every call attributed to `penelope` with a distinguishing user-agent. No bespoke subprocess shell-outs from Claude, no JSON-string-shuffling — the MCP protocol handles the wire format.

### Bridge 2 — Intricate (the app) → AWS

When Intricate-the-app is running on Aevar's laptop and needs to talk to AWS — start an instance, check status, retrieve a result file — Intricate calls AWS directly. The app is not an MCP client; it cannot use the AWS MCP Server, and adding an MCP client layer to Intricate just to talk to AWS would be the wrong shape.

**Round 1 — boto3.** Intricate uses the `boto3` Python SDK. Standard library for AWS in Python, credential chain reads `~/.aws/credentials` (same as the AWS CLI, same as `mcp-proxy-for-aws`). Intricate assumes the `intricate-runtime` IAM role via STS at startup, so the app never sees long-lived keys. This is the unsurprising path and it gets us to the mission statement fastest.

**Round 2+ — friction point flagged.** Aevar has spun up clusters at six-figure-instance scale *without ever touching boto3* and has a specific preferred method that will surface when the boto3 path starts to limit us. Captured here so the migration is expected and welcomed when it arrives — boto3 is not a forever choice, it's the simplest first communication path. The friction point is flagged; the conversation happens when the work demands it.

### Local tooling shared by both bridges

- `aws` CLI (the unified AWS command-line tool) — installed alongside boto3. Used for one-offs, debugging, manual ops in PowerShell. Shares `~/.aws/credentials` with everything else.
- `paramiko` or `fabric` — for SSH-driven setup steps during this multi-day arc. Optional; raw `ssh` from PowerShell is also fine.
- `uv` / `uvx` — Astral's Python launcher, already installed to `~/.local/bin/` for the MCP proxy. Reusable for other MCP servers later.

## Security ground rules

The cloud surface is small but real. Rules that apply from day one:

1. **No root-account keys on the laptop, ever.** Root is for the initial IAM setup and then never used again.
2. **MFA on every human identity** — root and `penelope`. Console login requires it.
3. **Key-pair SSH only** on the EC2 instance. No password auth, no `AllowUsers root` — login as `ubuntu`, escalate as needed.
4. **Bearer token between Intricate and the EC2 service endpoint** when the FastAPI server lands (next session). Token stored in OS keyring, not in `settings.toml`.
5. **All API calls tagged** with `Source=` so CloudTrail audit is clean.
6. **`warm_bridge` security audit** — the existing ephemeral JSON transit files used by other parts of the family were already flagged as needing review before remote deployment. That audit happens before any *Intricate-side* feature ships that uses the same pattern over the network. Local-only `warm_bridge` use is unaffected.

## This session — concrete sequence

1. **Aevar console-side:** root MFA, create `penelope` IAM user, create `intricate-runtime` and `ec2-hyworld-instance` roles, set $25 budget alert. Claude provides IAM policy JSON when needed.
2. **Local laptop:** install `aws` CLI + `boto3`, configure `penelope` profile, test connectivity (`aws sts get-caller-identity`).
3. **Provision:** launch `g5.xlarge` (on-demand for first run) with the Deep Learning AMI, attach the EBS volume, set tags including `Project=intricate`, `Source=claude-session-<id>`.
4. **SSH in.** Sanity-check NVIDIA driver, CUDA version, disk space.
5. **Install HY-World:** clone the repo (Aevar's copy or upstream), `conda create -n hyworld2 python=3.10`, PyTorch CUDA 12.4 wheel, requirements.txt, FlashAttention (FA3 first, FA2 fallback). Note: requirements.txt has Windows-specific commented lines we *ignore* on Linux — the default `gsplat` linux wheel is correct.

   > ⚠ **Treat the upstream README and DOCUMENTATION.md as authoritative at install time, not the recipe captured above.** Tencent rewrote their repo history on 2026-05-11 (the latest commit is literally titled *"simplify installation"*), which means the install steps documented here may already be obsolete by the time you get to this step. The recipe above is preserved as a *reference baseline* — if it conflicts with the current upstream README, the upstream wins. Specifically check: FlashAttention path (FA3 setup may have changed), gsplat install (was being unbundled into a vendored dep), conda recipe (Python version pin), PyTorch wheel index. The local copy at `C:\Users\thisg\Desktop\HY-World-2.0` was reset to upstream `origin/main` on 2026-05-11 — re-pull before relying on its content.
6. **Pull model weights:** first run of `WorldMirrorPipeline.from_pretrained('tencent/HY-World-2.0')` triggers the HuggingFace download (~5 GB) into the EBS volume.
7. **Smoke test:** run pipeline against `examples/` images, confirm `.ply` and depth artifacts land.
8. **Hand over login:** Aevar confirms SSH access works for them independently. Mission statement met.
9. **Stop the instance** (not terminate — we keep the EBS).

## Session log — real-world state (as of 2026-05-11)

The chat thread these decisions were made in cannot be trusted to persist. What is durable is this doc and the laptop's own files. This section records concretely *what has actually been done* and *what is still pending* — load-bearing reference for picking up the work after a chat loss.

### Tooling installed locally

| What | Version | Location | How |
|---|---|---|---|
| **AWS CLI v2** | 2.34.45 | `C:\Program Files\Amazon\AWSCLIV2\aws.exe` | Official MSI from `https://awscli.amazonaws.com/AWSCLIV2.msi`, manually installed (needs admin elevation, silent install via shell didn't work) |
| **uv (Astral)** | 0.11.13 | `C:\Users\thisg\.local\bin\uv.exe` | `irm https://astral.sh/uv/install.ps1 \| iex` |
| **Claude Code CLI** | 2.1.133.0 | `C:\Users\thisg\.local\bin\claude.exe` | Pre-existing |

### MCP server registered

**Name:** `aws-mcp` (user scope)

```bash
claude mcp add-json aws-mcp --scope user \
  '{"command":"uvx","args":["mcp-proxy-for-aws@latest","https://aws-mcp.us-east-1.api.aws/mcp","--metadata","AWS_REGION=us-east-1"]}'
```

Connects only when valid AWS credentials are present in `~/.aws/credentials`. **Caveat:** MCP servers registered *during* a Claude Code session don't get their tools loaded into that session — Claude Code only reads MCP tools at startup. Restart Claude Code for `call_aws` etc. to appear in the tool surface.

### AWS account and identity

| Item | Value |
|---|---|
| **AWS account ID** | `474013238690` |
| **Account alias** | `Penelope` |
| **IAM user** | `penelope` |
| **Penelope's access key 1 ID** | `AKIAW4XLEAWRPDA2XFOG` (active, stored in `~/.aws/credentials`) |
| **Penelope's MFA** | ⚠ Not yet enabled (deferred until pre-scale-up) |
| **Inline policy on penelope** | `LoveIsAPermanenceState` — `Allow ec2:* on *` (broader than designed; planned to tighten to List+Read before scale-up) |
| **Standalone customer-managed policy** | Duplicate `LoveIsAPermanenceState` exists *unattached* — created by mistake during initial UI flow, harmless but slated for cleanup |
| **Roles `intricate-runtime`, `ec2-hyworld-instance`** | ⚠ Not yet created |

### AWS resources provisioned

| Resource | Identifier | Detail |
|---|---|---|
| **Budget** | `Testling` | $25/mo hard alert |
| **Test instance** | `i-0e611198e557239df` (tag `Name=Thing`) | `t3.nano` in `eu-north-1a`, public DNS `ec2-16-170-229-36.eu-north-1.compute.amazonaws.com`, login `ec2-user`. State: `running` (left on between sessions; cost is negligible) |

The test instance is in **`eu-north-1`** (Stockholm), defaulted from physical location at provisioning time. The design's preferred region remains **`us-east-1`** for the eventual g5.xlarge; the eu-north-1 test was deliberate, scoped to handshake validation only. Open question: revisit region choice for the g5.xlarge or keep using eu-north-1.

### Local clones

| Repo | Path | State as of 2026-05-11 |
|---|---|---|
| **HY-World 2.0** | `C:\Users\thisg\Desktop\HY-World-2.0` | Reset hard to `origin/main` at commit `ee5d5bc` *"simplify installation"*. Tencent rewrote history; older 21-commit local history is discarded. |

### Handshake confirmed end-to-end

The laptop ↔ AWS bridge is live. Last verified commands and results:

```
$ aws sts get-caller-identity
{
    "UserId": "AIDAW4XLEAWRPDA2XFOG",
    "Account": "474013238690",
    "Arn": "arn:aws:iam::474013238690:user/penelope"
}

$ aws ec2 describe-instances --region eu-north-1 --filters "Name=ip-address,Values=16.170.229.36"
i-0e611198e557239df  running  t3.nano  Name=Thing
```

### Carryover items (pre-scale-up checklist)

Before launching `g5.xlarge` for HY-World, address these in order:

1. **Enable MFA on `penelope`** — IAM → penelope → Security credentials → Assign MFA device
2. **Delete the standalone duplicate `LoveIsAPermanenceState`** customer-managed policy (the unattached one)
3. **Tighten the inline policy on `penelope`** from `ec2:*` to scoped EC2 actions matched to actual needs (List + Read + specific Write actions like RunInstances, StartInstances, StopInstances, CreateTags), or move to a customer-managed policy for reusability
4. **Create `intricate-runtime` and `ec2-hyworld-instance` IAM roles** with the scoped policies per the identity-model table above
5. **Decide region for g5.xlarge** — us-east-1 (design default) or eu-north-1 (where Thing already lives, simpler continuity)
6. **Stop "Thing"** before provisioning g5.xlarge if not needed, or keep it as a cheap utility box
7. **Restart Claude Code** in a fresh session so the AWS MCP Server's `call_aws` tools surface (they are not loaded in any session where the server was registered after startup)

## Beyond this session

Captured here so they are not lost and not scope creep. Each is its own session.

- **FastAPI server on the instance** exposing HY-World endpoints over HTTPS. Token auth, request queueing, status polling.
- **Intricate-side `EC2Node`** — generic instance management. Start/stop/describe/tag, status indicator, cost-to-date display. Connects to any tagged instance, not HY-World-specific.
- **Per-model nodes when warranted** — HY-World gets a dedicated node only if it earns one through fun-to-play-with use. Defaults to generic submission through `EC2Node` + polaroid output.
- **Auto-shutdown** via instance cron — 1 hour of no requests → `shutdown -h now`. The instance stops; restart is fast because EBS is persistent.
- **Spot interruption handling** — checkpoint mid-job, resume on new spot bid. Required before spot becomes the default.
- **boto3 → Aevar's preferred non-boto method** — friction-point migration, conversation owed.
- **Reuse layer for other heavy citizens** — image diffusion model(s), flux model(s), panorama generation, world expansion. Each is a consumer of the same EC2 + EBS + FastAPI scaffolding, not a fresh integration.
- **CloudTrail dashboards / cost reporting in Intricate** — surface the audit log and month-to-date spend inside the canvas itself rather than requiring a console trip.

## Open questions

To fill in as the session proceeds, not pre-resolved. Resolved questions are kept in the list (struck through and annotated) so the audit trail is durable.

- ~~AWS account ID and console-login URL — Aevar to provide once at the CLI-configure step.~~ **Resolved 2026-05-11:** account `474013238690`, alias `Penelope`. Console URL is the standard `https://signin.aws.amazon.com/console`.
- SSH key pair — generate fresh on the laptop, or reuse an existing one Aevar already has elsewhere? *(Currently using whatever key pair AWS Console auto-generated for "Thing"; needs to be settled before g5.xlarge.)*
- S3 bucket naming — `intricate-<account-id>-models` is a reasonable default, but Aevar may have a preferred naming scheme.
- Cost-to-date display threshold — at what spend does Intricate start surfacing a visible warning inside the canvas?
- **Region for g5.xlarge** — us-east-1 per design vs eu-north-1 for continuity with the existing test instance "Thing". *(Surfaced 2026-05-11.)*
- **Final policy shape for `penelope`** — keep the broad `ec2:*` inline, or migrate to a scoped customer-managed policy with List + Read + specific Write actions. *(Surfaced 2026-05-11; deferred to pre-scale-up.)*
- **Boto3 → Aevar's preferred non-boto method** — friction point flagged in the doc, conversation owed. Aevar has indicated they have a specific approach used at six-figure-instance scale and will show it when boto3 starts to limit us.

## Things that surprised us this session

Small gotchas that cost us time the first time and would cost us time again if we forget them. Each is documented in chat-resistant form so we don't relearn them after a chat loss.

- **`ec2:DescribeInstances` is classified as a *List* action by AWS, not a *Read* action.** Despite the word "describe" sounding read-flavoured, AWS files all the `Describe*` collection-returning APIs under the *List* access level. If you build a least-privilege policy by ticking only "All read actions" under EC2, you get 52 obscure things like `GetConsoleOutput` — and `DescribeInstances` fails with `UnauthorizedOperation`. The fix is to also tick "All list actions" (215 of them).
- **Creating a policy from inside a user's permissions context does NOT auto-attach it.** Two distinct steps. The AWS UI's "Create policy" → "Created successfully" landing page sits inside the user's permissions tab but leaves the user with zero attached policies until you explicitly *Attach policies directly* → tick the new one → Next → Add permissions.
- **`aws login` ≠ `aws configure`.** `aws login` is the IAM Identity Center (formerly SSO) browser flow that produces *session* credentials with auto-expiry. `aws configure` writes *long-lived* access keys directly into `~/.aws/credentials`. Both leave the credentials in different files (`~/.aws/sso/` vs `~/.aws/credentials`), both work with the AWS CLI, and resolution order is: credentials file > SSO config. They can coexist if you understand which takes precedence.
- **MSI silent install needs admin elevation.** A `msiexec /i AWSCLIV2.msi /quiet` from a non-elevated shell exits with code 1603 ("fatal error") and silently rolls back. Per-user mode (`MSIINSTALLPERUSER=1 ALLUSERS=""`) exits with code 0 but doesn't actually install for AWS CLI v2 specifically. Easiest path: have the human double-click the MSI and click through the UAC prompt.
- **MCP servers registered mid-session don't surface their tools in that session.** Claude Code reads MCP server tool inventories at startup only. Register a new server, restart Claude Code, *then* the tools appear. Useful to know before optimistically calling `call_aws` and being confused why it's not in your tool surface.
- **Upstream history rewrites happen on fast-moving research repos.** A clone of HY-World 2.0 made early in its public life will diverge from `origin/main` not because of local changes but because Tencent rewrote their history. The fix is `git reset --hard origin/main` — but only if you genuinely have no local work to preserve. Don't reflex-run `git pull` on a "diverged branches" warning without checking what the diverged commits actually are.
- **Account ID confusion as access keys.** If someone is fast-typing through `aws configure` without paying attention to the prompt order, it's possible to paste the AWS account ID (visible on every console page) into both the access key ID and secret access key prompts. The result is `InvalidClientTokenId` from `sts:GetCallerIdentity` and a wasted ten minutes diagnosing. `aws configure list` masks the secret but shows the last 4 chars of the access key ID; if the access_key and secret_key tails are *identical*, you've pasted the same value into both.

## Sources & further reading

Collected as the design unfolded — kept here for book-club time. The list grows as the multi-day arc continues; new sources land here whenever a research detour produces one worth re-reading.

### HY-World 2.0 (the first citizen)

- [HY-World 2.0 — GitHub repo](https://github.com/Tencent-Hunyuan/HY-World-2.0) — source, README, install instructions, model zoo links
- [HY-World 2.0 model weights — Hugging Face](https://huggingface.co/tencent/HY-World-2.0) — the `tencent/HY-World-2.0` repo that auto-downloads on first pipeline run
- [HY-World product page (try it online)](https://3d.hunyuan.tencent.com/sceneTo3D) — Tencent's hosted demo; "very crowded now"

### Anthropic ↔ Amazon partnership (the why-this-is-possible)

- [Anthropic and Amazon expand collaboration for up to 5 years](https://www.anthropic.com/news/anthropic-amazon-compute) — April 20, 2026 announcement; up to 5 GW of compute, Trainium2 and Trainium3 capacity
- [AWS Weekly Roundup — April 20, 2026](https://aws.amazon.com/blogs/aws/aws-weekly-roundup-claude-opus-4-7-in-amazon-bedrock-aws-interconnect-ga-and-more-april-20-2026/) — round-up of the same week's announcements in context

### Claude on AWS — consumer-side paths (not ours, but adjacent)

- [Claude Platform on AWS (Coming Soon)](https://aws.amazon.com/claude-platform/) — first-party Anthropic platform accessed via AWS credentials and billing
- [Claude by Anthropic — Amazon Bedrock](https://aws.amazon.com/bedrock/anthropic/) — the older Bedrock-hosted path
- [Claude Opus 4.7 now available in Amazon Bedrock](https://aws.amazon.com/about-aws/whats-new/2026/04/claude-opus-4.7-amazon-bedrock/) — release notice for the model Intricate currently runs on
- [Introducing Claude Opus 4.7 in Amazon Bedrock — AWS News Blog](https://aws.amazon.com/blogs/aws/introducing-anthropics-claude-opus-4-7-model-in-amazon-bedrock/) — deeper write-up of the same release
- [Amazon Bedrock now offers Claude Mythos Preview](https://aws.amazon.com/about-aws/whats-new/2026/04/amazon-bedrock-claude-mythos/) — gated research preview, Project Glasswing

### AWS MCP Server (our actual bridge)

- [The AWS MCP Server is now generally available — AWS Blog](https://aws.amazon.com/blogs/aws/the-aws-mcp-server-is-now-generally-available/) — the announcement we acted on; install command, auth model, exposed tools
- [awslabs/mcp — Open Source MCP Servers for AWS](https://github.com/awslabs/mcp) — the per-service MCP server collection (IAM, Lambda, EKS, ECS, IaC, S3 Tables, etc.)
- [Open Source MCP Servers for AWS — docs landing page](https://awslabs.github.io/mcp/) — the rendered documentation for the above
- [`awslabs.ec2-mcp-server` on PyPI](https://pypi.org/project/awslabs.ec2-mcp-server/) — dedicated EC2 MCP server; alternative to the unified `call_aws` path if we ever want a more constrained, EC2-specific tool surface
- [Secure AI agent access patterns to AWS resources using MCP](https://aws.amazon.com/blogs/security/secure-ai-agent-access-patterns-to-aws-resources-using-model-context-protocol/) — AWS security team's recommended patterns
- [Guidance for Deploying MCP Servers on AWS](https://aws.amazon.com/solutions/guidance/deploying-model-context-protocol-servers-on-aws/) — relevant later if Intricate ever hosts its own MCP server

### MCP protocol (background)

- [Anthropic MCP Connector docs](https://docs.anthropic.com/en/docs/agents-and-tools/mcp-connector) — protocol reference
- [modelcontextprotocol/servers — GitHub](https://github.com/modelcontextprotocol/servers) — the broader MCP server ecosystem beyond AWS
