# wotclock

An Observable Notebook Kit recreation of *wotclock* (2002/2005), a QuickTime 'speaking clock' made in LiveStage. Co-implemented with Claude Sonnet 5.5.
The notebook entry point is `nbks/index.html`.

## Commands

- `npm run preview` — local preview at http://localhost:5173 (add `?time=14:07:30` to start the clock at a chosen time)
- `npm run build` — build to `dist/`
- `python3 tools/extract.py` — regenerate `nbks/data/` from `raw/wotclock/` (needs `ffmpeg`; `raw/` is not tracked)

## How the original works (and where it lives here)

`clock.mov` is a small master movie. Its `mainspring` sprite track holds one idle handler written as QuickTime
wired actions; it was decoded from the movie and ported to `nbks/data/clock.js` (`createMainspring`).
Everything else is a track of `clock.mov`, or an external movie it loads:

| Original | Here |
| --- | --- |
| `pauls.mov` — St Paul's QTVR panorama with the 24 hour numerals painted in, plus a ruler/vignette overlay | `pano/pauls.jpg`, `pauls-overlay.png`; panned to an analogue reading of the time (`HOUR_PAN`, `analogPan`) |
| `clockscene.mov`, `whisperscene.mov` — 24 panoramic nodes each, one per hour (nodes 25–48 and 1–24); both slowly turn | `pano/scene-NN.jpg`, `pano/whisper-NN.jpg`; the scene and whisper layers swap on some minutes |
| `clockface` — an embedded movie of 12 letter cells (e t a n i o s l r, e=1 … r=9); the red letter is the second hand, 5 s per cell | `DIAL`, `dialIndex` |
| `clockhands` — `hnds/c01..c24hands.txt`, one phrase per 4 s of the hour, with the time in red mesostic letters | `hands.json`, indexed by hour file and `minute*60+second` |

Panorama conventions recovered from the QTVR sample atoms, implemented in `nbks/data/panorama.js` (WebGL2):
stored rotated 90°, tiles stacked, columns run in the direction of decreasing pan, rows are linear in tan(tilt),
field of view is vertical.

## Differences from the original

- The idle rate of the scene rotation is not stored in the movie (0.05° per idle); `IDLE_HZ` in `clock.js` sets it.
- The PC variants of the text (`hndspc/`, Courier) are not used; the Mac variant is.
- QTVR hotspots in `clockscene.mov` have empty URLs, so nothing is lost by omitting them.
- The scenes are rendered with bicubic sampling, a sharper mip bias and a light unsharp mask (`?sharpen=N`, 0 turns it off),
  because the 2002 JPEG sources are soft and are shown at 0.7–1.0× of source pixels (more on high-DPI screens).
- Next hour's panoramas are preloaded from :59:30, and phrases have a small text shadow for legibility.
