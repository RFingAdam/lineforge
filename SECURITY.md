# Security Policy

## Reporting a vulnerability

lineforge is a numerical-computation library — most security-relevant issues
involve untrusted inputs flowing into the solver pipeline. Specifically:

- Maliciously-crafted BMP/PNG/TIFF usermaps (Pillow decoder vulnerabilities,
  zip-bomb-style decompression, buffer over-reads).
- Crafted `MoreColors.txt` or atlc2 `.txt` script files.
- Crafted JSON geometry blobs reaching the MCP tools.
- Resource exhaustion via the MCP `solve_cgp` tool (large grids, runaway
  iteration counts).
- Path-traversal in the MCP `import_usermap` / `run_atlc2_script` tools.

If you find one of these, please **do not open a public issue**.

### How to report

- **Preferred:** GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  on the [security tab](https://github.com/RFingAdam/lineforge/security/advisories/new).
- **Email fallback:** open a minimal private issue requesting a contact
  channel. We'll set up a private discussion.

Please include:

- Affected version (output of `lineforge --version`).
- Minimal reproduction (commands or a small test case).
- Impact assessment (confidentiality / integrity / availability, severity).
- Whether you have a proposed fix.

## Response timeline

- **Acknowledgement:** within 7 days.
- **Triage + severity assessment:** within 14 days.
- **Coordinated disclosure window:** 90 days from acknowledgement, or
  sooner if a fix lands and we agree.

We follow [coordinated vulnerability disclosure](https://www.first.org/global/sigs/vulnerability-coordination/multiparty/).

## Supported versions

While the project is pre-1.0, only the `main` branch and the latest tagged
release receive security fixes. After 1.0.0, we'll publish a support matrix
here matching SemVer minor versions.

## Scope

In scope:

- The `lineforge` Python package and its native `lineforge._kernel` extension.
- The `lineforge-mcp-serve` MCP stdio server.
- The CLI (`lineforge ...` commands).
- atlc2 file-format parsers (BMP, MoreColors.txt, .txt scripts).

Out of scope:

- Vulnerabilities in upstream dependencies (numpy, scipy, pillow, mcp,
  pyo3, …) — please report those upstream. We'll bump versions promptly
  once upstream fixes ship.
- Issues that require a malicious local user with filesystem access (this
  is a user-installed tool, not a server).
- Cosmetic security warnings from static analysers without a demonstrated
  attack path.

## Hardening notes for users

If you run the MCP server somewhere it accepts untrusted inputs:

- The `import_usermap` tool decodes base64 BMPs via Pillow. Pillow has had
  decoder CVEs in the past; pin to a recent version.
- The `run_atlc2_script` tool's `open <path>` command can read filesystem
  paths. Run the server in a sandbox (container, restricted user) if the
  client is untrusted.
- The async `solve_cgp` task uses `asyncio.to_thread` — long solves can
  pin a CPU core. Use `tasks_cancel` to bound runtime, or a timeout
  reverse-proxy in front of the server.
