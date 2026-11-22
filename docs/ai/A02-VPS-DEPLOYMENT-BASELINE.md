# S3-Voice-AI — A02 VPS deployment baseline, isolation, and rollback gate

**Date:** 2026-11-22  
**Delivery:** Design, original-source audit, safe read-only inventory script, automated CI; no VPS/4B modification.  
**Evidence state:** Source/design/host inventory verified. User ran the pinned read-only inventory on the target Debian 13 VPS at **2026-11-22T11:37:29Z** and supplied sanitized output. No SSH access was used by the assistant. A02 is ready for merge once final-head GitHub CI is all green.  

## 1. GDGS scope / plan preserved

8 PRs in 4 stages: P0 A01(5%) + A02(5%), P1 A03(18%) + A04(12%), P2 A05(22%) + A06(13%), P3 A07(15%) + A08(10%). A01 merged as #21. A02 uses one PR only. R1 #15/#20 and R2 untouched. No feature implementation or new firmware.

A02 objective: assess existing Debian 13 server workload, select minimal mature deployment components, define strict host/network separation, secret handling, backup/rollback, and A03/A04 acceptance gates.

## 2. Existing host: historical versus current evidence

User's **2026-11-14 actual host output** listed:
- MiniProbe: miniprobe-server-1, miniprobe-cloudflared-1; historical loopback port 127.0.0.1:28888.
- HomeSphere: homesphere, homesphere-live-gateway (Caddy in host network mode), homesphere-tvb-egress, media-bridge, qms-postgres. Historical ports 127.0.0.1:8080, 127.0.0.1:12333, and host TCP/UDP :443 used by Caddy.
- On 2026-11-14, no listener was seen on TCP :8443. This is historical, not a guarantee of current availability.
- User's nominal VPS capacity: Debian 13, 2 vCPU, 4 GiB RAM, 60 GB disk. This is not a fresh command result and is **not sufficient evidence** of idle resources.

Source-only cross-check against private repositories (no secret contents copied):
- Jackyhuang83/HomeSphere docker-compose.yml binds 127.0.0.1:8080:8080, has live-gateway network_mode: host.
- HomeSphere docker-compose.bridge.yml binds 127.0.0.1:12333:12333.
- Jackyhuang83/MiniProbe contains deploy/docker.

**Verified at 2026-11-22T11:37:29Z:** Debian 13 / x86_64 / kernel 6.12.115+deb13.1-amd64 / 2 CPU; 3,753,804 KiB total memory and 2,145,920 KiB available (~2.05 GiB); 45,796,256 KiB available (~43.67 GiB) in both /opt and Docker backing filesystem; Docker Engine 29.9.3, Docker Compose 5.7.0. The user's captured container list includes HomeSphere, its host-mode Caddy, TVB egress, media-bridge, MiniProbe server/tunnel, and qms-postgres. TCP 80/443/8080/12333/28888 were listening; **18000/18003/18080 had no listener** at collection. /opt/homesphere and /opt/miniprobe-docker exist; /opt/s3-voice-ai does not yet exist. These are a timestamped host snapshot, not a persistent port reservation or complete service-health probe. Do not publish IPs, credentials, or private configs.

## 3. Why upstream Docker Compose is unsuitable as-is

Pinned source candidate: xinnan-tech/xiaozhi-esp32-server v0.9.8, release commit 8f2dda09cf18f1c1ece0f906eee4cc2fabb7fb58. Exact compose:
https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/docker-compose.yml

The original Compose:
- Runs floating mirror image ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:server_latest. A floating tag **does not prove** matching v0.9.8 source. A03 must establish source->image provenance and immutable digest, or build the exact pinned upstream Dockerfile without changing its code.
- Publishes 8000:8000 and 8003:8003 on all interfaces. A paid-API private application must not be opened directly on host-wide bindings.
- Includes seccomp:unconfined. A03 must try Docker default seccomp and preserve default permissions unless a necessary capability is demonstrated and approved.
- Mounts a SenseVoiceSmall ASR model. A03/A06 must first evaluate CPU/RAM against shared HomeSphere workload; prefer supported cloud ASR when local memory is insufficient and configure payment limits.
- Default server auth is disabled. v0.9.8 upstream allowed_devices bypasses token validation for listed Device-Ids, while non-listed callers may still obtain a signed token from the public OTA handler. This is **not strict device admission**.

References:
- https://docs.docker.com/engine/network/port-publishing/ — localhost published ports and pre-v28 security caveat.
- https://caddyserver.com/docs/caddyfile/directives/reverse_proxy — transparent WebSocket proxy.
- https://developers.cloudflare.com/network/websockets/ — Cloudflare WebSocket support.
- https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/protocols/ — private published hostnames.

## 4. Chosen isolated topology (proposed, NOT deployed)

| Service | Host bind, to be checked | Purpose |
|---|---|---|
| s3-voice-ai-server | 127.0.0.1:18000 -> container:8000 | Official XiaoZhi WebSocket |
| s3-voice-ai-server | 127.0.0.1:18003 -> container:8003 | Official OTA HTTP |
| Dedicated Caddy v2 ingress | 127.0.0.1:18080 | Path/method/device-pair admission + proxy |
| Dedicated Cloudflare Tunnel | Outbound only | Proposed hostname voice.cncloudx.com and HTTPS/WSS |

**Do not** touch HomeSphere host-mode Caddy :443, MiniProbe connector, HomeSphere/MiniProbe Compose projects, host firewall or any other live port. Do not add inbound 80/443/8000/8003 rules. A dedicated Tunnel/connector can reach a host-local gateway when installed in an appropriately isolated host networking context, but **its actual configuration and account availability are not confirmed**. The proposed hostname has NOT been created.

Logical project/paths: Compose project s3-voice-ai; /opt/s3-voice-ai for application; root-only /etc/s3-voice-ai (0700) for API keys, allowed-device fingerprints and Tunnel credential; /var/backups/s3-voice-ai (0700) for versioned config snapshots. No secrets or device UUID/MAC in the public repository, CI or normal logs. Existing HomeSphere/MiniProbe config files must never be dumped.

Architecture: 4B v2.6.0 -> Cloudflare HTTPS POST /xiaozhi/ota/ -> ingress -> official OTA -> JSON websocket.url wss://voice.cncloudx.com/xiaozhi/v1/ -> ingress -> official WS -> selected ASR/LLM/TTS. OTA returns **firmware.url empty**, never offers binary; MQTT branch absent. This does not require an ESP32 firmware flash.

## 5. Public-edge admission: conditional security acceptance, not security theater

- A04 must allow *only* a privately enrolled exact Device-Id AND Client-Id pair on OTA POST and WS upgrade. Other identities and paths (including OTA binary downloads) must fail **before** reaching the server. All other methods/routes denied except a deliberately local health check.
- Enable the official WebSocket token check **without** assuming it blocks arbitrary new devices: its original OTA handler can mint tokens for arbitrary submitted identities. The gateway admission check must cover both OTA and WS paths.
- Client-Id is persisted random UUID and not a cryptographic hardware attestation. Its confidentiality + both endpoints' TLS + log redaction are needed; this design has device-identity replay risk if headers leak. A04 security gate includes spoofing/unknown-device checks and paid API budget constraints.
- Cloudflare Access browser OTP is not compatible with noninteractive 4B client. Do not copy the existing F50 LuCI email challenge flow. Verify Tunnel/WebSocket connection at the edge, rate limiting/concurrency (only use controls actually available in the Cloudflare account), cost ceilings/alerts from each LLM vendor.
- Basic security is mandatory even though speculative failure cases below 20% are deferred.

## 6. Reproducible read-only host inventory (A02 tool)

Script: tools/ai/a02_vps_inventory.sh

Reports only OS ID/version, CPU architecture and count, available memory/disk, Docker Engine/Compose version, **selected** running container names, listener presence for known ports, and expected-directory existence. **It does not execute writes, restart services, run docker inspect, reveal env/config/hostname/IP/device IDs/keys, contact external services, or require root.**

After reviewing the script in the PR and from the exact reviewed Git commit, run this on the *same Debian VPS running HomeSphere + MiniProbe*:

~~~bash
curl -fsSLo /tmp/s3-voice-a02-readonly.sh \
  https://raw.githubusercontent.com/Jackyhuang83/s3-voice-4b-proxy/ai/p0-a02-vps-isolation-20261122/tools/ai/a02_vps_inventory.sh
bash -n /tmp/s3-voice-a02-readonly.sh && bash /tmp/s3-voice-a02-readonly.sh
~~~

The downloaded script creates a temporary local file but does not modify existing services. The command above reads the A02 PR branch; after final CI, pin the URL to its exact reviewed Git commit SHA for formal attestation. Do not substitute moving main until the PR is actually merged. Results may be shared without API credentials. If Docker is inaccessible, report inaccessible and do not ask user to run dangerous privileges. A no-listener snapshot is **not a guaranteed available port**; A03 checks binding again.

**A02 host-evidence exit checklist (fulfilled by supplied target host inventory; periodic recheck in A03):**
- Target actually identifies as Debian 13 with known architecture; adequate idle RAM and disk for a conservative cloud-ASR baseline.
- Docker Engine and Compose present; if Docker Engine <28, do not treat localhost-published Docker ports as an airtight security boundary without an alternative network isolation gate.
- Preserve identity and running footprint of HomeSphere, MiniProbe, Caddy, media-bridge; never restart them during A02.
- Confirm 18000, 18003 and 18080 have no current listener; A03 rechecks atomic bind.
- Record sanitized run timestamp and hash/commit of this inventory script. No secrets.

## 7. A03 and A04 implementation, release, and rollback gates

A03 (next stage, not part of A02):
1. Create independent repository s3-voice-ai-server after A02 final decision, or document why the existing repo remains preferable; preserve R1/R2 proxy tracks.
2. Pin a provenance-verified image digest; use isolated Compose and server resource caps established from actual host inventory. No floating latest, no seccomp:unconfined by default, no public binds.
3. Test official OTA POST (not only browser GET); must return correct WSS endpoint, no MQTT and **empty firmware URL**. If upstream cannot satisfy this without changes, reject image and choose a safe configuration-compatible candidate rather than writing a new OTA engine.
4. Only manage s3-voice-ai Compose services; backup its own config/image hashes and private credential files, never remove original workload. No docker system prune, daemon/network reset, or host firewall changes.

A04:
1. Automated known-device success, unknown-device rejection and spoofed header cases on both OTA and WebSocket, plus WebSocket hello v1 / raw Opus.
2. TLS/WSS through Cloudflare Tunnel and request-path gating verified; deny OTA download paths. Validate actual Cloudflare plan limitations before relying on any paid WAF feature.
3. Safe disable/rollback: stop dedicated tunnel + AI project only; original HomeSphere/MiniProbe remain online; 4B may restore its original OTA preference in P3 without flashing.
4. Provider-side budget and key management; API keys never on firmware/GitHub.

## 8. Evidence ledger / verdict

| Claim | Evidence level | A02 status |
|---|---|---|
| Historical services & ports | User actual outputs + project source | HISTORICAL, not 2026-11-22 live |
| Upstream Docker defaults | v0.9.8 source | SOURCE VERIFIED |
| Docker/Tunnel/Caddy feasibility | Official documentation | DOCUMENTED ONLY |
| Host inventory script privacy/read-only | File review + GitHub CI | PASS (previous HEAD) — final HEAD pending |
| Actual target VPS spare resources, ports & Docker version | User provided script output 2026-11-22T11:37:29Z | **PASS** for A02 snapshot, recheck bind in A03 |
| Image digest/source provenance | To be verified in A03 | NOT RUN |
| Current public Tunnel & device admission | To be verified in A04 | NOT RUN |

**A02 CONDITIONAL GO for A03:** Target host inventory has now been supplied and meets the planning acceptance gate. **No VPS changes have been made and production exposure remains BLOCKED until A04 security gates pass.** A02 can count only after CI is green on the new final HEAD and PR is merged. Before merge: P0=50%, overall=5%; after merge: P0=100%, overall=10%.


## 9. Live A02 evidence addendum — accepted snapshot

Captured via the PR-pinned read-only script as supplied directly by the user, **2026-11-22T11:37:29Z**, on the server running both HomeSphere and MiniProbe. This is user-executed host evidence, not assistant SSH access or an ESP32 board test.

```text
S3_VOICE_AI_A02_INVENTORY_V1
timestamp_utc=2026-11-22T11:37:29Z
os_id=debian
os_version_id=13
arch=x86_64
kernel=6.12.115+deb13.1-amd64
cpus_online=2
memory_total_kib=3753804
memory_available_kib=2145920
disk_available_kib_opt=45796256
disk_available_kib_docker=45796256
docker_cli=present
docker_engine_version=29.9.3
docker_compose_version=5.7.0
known_running_containers=homesphere,homesphere-live-gateway,homesphere-tvb-egress,media-bridge,miniprobe-cloudflared-1,miniprobe-server-1,qms-postgres
tcp_port_80=listening
tcp_port_443=listening
tcp_port_8000=no_listener_seen
tcp_port_8003=no_listener_seen
tcp_port_8080=listening
tcp_port_12333=listening
tcp_port_28888=listening
tcp_port_18000=no_listener_seen
tcp_port_18003=no_listener_seen
tcp_port_18080=no_listener_seen
homesphere_dir=present
miniprobe_dir=present
s3_voice_ai_dir=absent
A02_INVENTORY_END
```

**A02 acceptance:** PASS for host inventory (timestamped), resource candidate suitability, observed port coexistence, and unchanged existing project status in the read-only observation. This does not establish free memory under all workloads, container application health, cloudflared account permissions or any working OTA/WS service. A03 must recheck all three bind ports atomically, confirm resource and image provenance, and deploy only after its own acceptance checks. A04 is responsible for pre-publication device authentication and billing protection.
