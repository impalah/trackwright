# Security policy

**English** · [Español](SECURITY.es.md)

## Supported versions

Only the latest version published on PyPI receives fixes.

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting: **Security → Report a vulnerability** in the repository. Include the version, what an attacker can do and how to reproduce it.

You will get an answer as soon as possible. This is a personal project maintained in spare time, so there is no fixed response time.

## What Trackwright exposes

- No network port. `trackwright serve` talks to its MCP client over stdio; the bridge listens on a Unix socket in a private directory (mode 0700) owned by the user.
- Two virtual MIDI ports, used only by the Cubase script. Trackwright never sends to physical devices or "All MIDI Inputs".
- Writes to the Cubase project are off by default (`[writes] enabled = false`), can be limited to some tracks, and saving needs its own switch (`[writes] save`).
- Reading audio is off by default (`[analysis] enabled = false`). When enabled, Trackwright reads the samples of the files it is asked to analyze (exports the user made), read-only and limited in duration (`[analysis] max_seconds`); only the measurements leave the process, as answers to the MCP client.
- Writing in a project folder is off by default (`[workspace] enabled = false`). When enabled, Trackwright writes only inside a `Trackwright/` folder there; every path is checked to stay inside it, and a `Trackwright` that is a symbolic link is refused.

Reports about these boundaries (another local user reaching the socket, a client bypassing the write policy, a command that writes when it should only read) are the most useful.
