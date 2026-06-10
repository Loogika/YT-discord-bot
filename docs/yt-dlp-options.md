# yt-dlp Options

LoogikaBot uses separate yt-dlp option sets because search and playback have
different performance requirements.

## Current strategy

### Shared options

```python
{
    "noplaylist": True,
    "quiet": True,
    "source_address": "0.0.0.0",
    "socket_timeout": 20,
    "retries": 3,
    "fragment_retries": 3,
}
```

- `noplaylist`: do not resolve a video URL as a playlist.
- `quiet`: suppress normal terminal output; warnings and errors go through the
  application logger.
- `source_address`: forces IPv4. This can avoid broken IPv6 routes, but should
  be tested again on the VPS.
- `socket_timeout`: limits how long an unresponsive YouTube request can block.
- `retries`: retries ordinary extraction and HTTP failures.
- `fragment_retries`: retries HLS/DASH fragments when such a format is used.

### Candidate search

```python
{
    "extract_flat": "in_playlist",
    "skip_download": True,
}
```

Text input is converted explicitly to `ytsearch10:<query>`.

`extract_flat` is the main search optimization: yt-dlp returns lightweight
metadata for candidates without fully resolving every video and its formats.
Only the user-selected result is resolved for playback.

### Stream resolution

```python
{
    "format": (
        "bestaudio[protocol^=http][vcodec=none]/"
        "bestaudio[protocol^=http]/"
        "bestaudio/best"
    ),
    "skip_download": True,
}
```

The selector prefers direct HTTP(S) audio-only formats before falling back to
other audio formats. Avoiding HLS where possible may reduce manifest delays,
but it does not solve network-level z4 or z5 disconnects.

## Common options worth considering later

- `proxy`: route yt-dlp requests through a dedicated proxy. Useful for z1, but
  FFmpeg must use the same route or stream URLs may fail.
- `cookiefile`: use exported YouTube cookies for age-restricted or authenticated
  content. The file must be treated as a secret.
- `geo_bypass_country`: request content as a specific country where supported.
- `extractor_args`: configure YouTube player clients. Powerful but fragile;
  only add after measuring a specific extraction problem.
- `format_sort`: prefer codecs, bitrates, or protocols more precisely.
- `sleep_interval_requests`: reduce request rate. Useful against throttling, but
  intentionally slows search.
- `concurrent_fragment_downloads`: speeds fragmented downloads. It provides
  little value for direct Discord streaming and increases network load.
- `cachedir`: controls yt-dlp cache. Keeping the default cache is generally
  useful on a persistent VPS, but containers need a mounted volume to preserve
  it across recreation.

## Options intentionally avoided

- `default_search="auto"`: convenient for a one-result bot, but hides whether
  input became a search, channel, or playlist. Explicit `ytsearch10:` is safer.
- high retry counts: they make `/play` appear frozen during z1/z4 failures.
- `ignoreerrors`: can silently convert real extraction failures into missing
  entries and makes diagnostics harder.

Official reference:

- <https://github.com/yt-dlp/yt-dlp#usage-and-options>
- <https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp>
- <https://github.com/yt-dlp/yt-dlp#format-selection>
