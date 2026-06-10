# Known Issues

This file keeps stable names for recurring runtime problems across development
sessions and chats.

## z1: YouTube network connection failure

Symptoms:

- `WinError 10054`
- SSL handshake timeout
- `TransportError`
- `UNEXPECTED_EOF_WHILE_READING` during search or extraction

Meaning: the bot cannot reliably reach YouTube. This is usually caused by the
local network, provider restrictions, VPN routing, firewall, or HTTPS filtering.

Current mitigation: use a working network route or VPN.

## z2: Missing JavaScript runtime or EJS components

Symptoms:

- `No supported JavaScript runtime could be found`
- yt-dlp warns that YouTube extraction without a JS runtime is deprecated

Meaning: yt-dlp cannot execute YouTube JavaScript challenges and may miss
formats or fail extraction.

Current mitigation: the Docker runtime contains Deno and `yt-dlp-ejs` through
`yt-dlp[default]`.

## z3: Search resolves to a non-playable result

Symptoms:

- a channel, playlist, or another collection is selected instead of a video
- extraction succeeds but no playable audio stream is available

Meaning: automatic search selected the wrong result type.

Current mitigation: text searches return up to ten flat video candidates and
require the user to choose one before it is queued. Direct URLs still bypass
the selection step.

## z4: YouTube stream fails permanently

Symptoms:

- FFmpeg exits with code `1`
- `googlevideo` returns `403 Forbidden`
- playback stops after TLS, HTTP, or `End of file` errors
- the current track is lost or skipped

Meaning: the resolved YouTube stream URL or CDN connection cannot be recovered.

Planned mitigation: resolve a fresh stream URL and retry the current track with
a bounded retry count.

## z5: YouTube stream disconnects but recovers

Symptoms:

- `Stream ends prematurely`
- `Error in the pull function`
- `IO error: End of file`
- `Will reconnect at ...`
- audio disappears briefly and then resumes

Meaning: a long-running HTTPS connection is periodically interrupted, commonly
by VPN or network routing, but FFmpeg reconnects successfully. Unlike z4, the
track continues playing.

Current mitigation: FFmpeg reconnect options are enabled. The issue is audible
but non-fatal. Compare VPN routes and reconnect intervals to identify the
network component closing the stream.
