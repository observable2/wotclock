#!/usr/bin/env python3
"""Extract the wotclock QuickTime project (raw/wotclock) into web assets in nbks/data.

Reads only the QuickTime container structure and the QTtext files; no QuickTime needed.
Requires ffmpeg on the PATH (used only to stitch/rotate the JPEG tile samples).

  python3 tools/extract.py

Writes:
  nbks/data/pano/pauls.jpg, whisper-01..24.jpg, scene-01..24.jpg   upright cylindrical panoramas
  nbks/data/pauls-overlay.png                                      overlay track of pauls.mov
  nbks/data/panos.json                                             view limits/defaults per panorama
  nbks/data/hands.json                                             the 24 x 900 phrases (hnds/c01..c24)
"""
import json, re, struct, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "wotclock"
OUT = ROOT / "nbks" / "data"


# ---------- QuickTime atoms ----------

def atoms(d, off, end):
    while off + 8 <= end:
        size, typ = struct.unpack(">I4s", d[off:off + 8])
        hdr = 8
        if size == 1:
            size = struct.unpack(">Q", d[off + 8:off + 16])[0]
            hdr = 16
        if size == 0:
            size = end - off
        yield typ, off + hdr, off + size
        off += size


def child(d, span, typ):
    for t, a, b in atoms(d, *span):
        if t == typ:
            return a, b


def qtatoms(d, off, end):
    """Parse a QTAtomContainer body into nested dicts {type, id, children|data}."""
    out = []
    while off + 20 <= end:
        size, typ, aid, _, nch, _ = struct.unpack(">I4sIHHI", d[off:off + 20])
        if size < 20:
            break
        node = {"t": typ.decode("latin1"), "id": aid}
        if nch:
            node["c"] = qtatoms(d, off + 20, off + size)
        else:
            node["d"] = d[off + 20:off + size]
        out.append(node)
        off += size
    return out


def qtfind(nodes, typ):
    for n in nodes:
        if n["t"] == typ:
            return n
        if "c" in n:
            r = qtfind(n["c"], typ)
            if r:
                return r


class Movie:
    def __init__(self, path):
        self.d = Path(path).read_bytes()
        moov = child(self.d, (0, len(self.d)), b"moov")
        self.tracks = []
        for t, a, b in atoms(self.d, *moov):
            if t == b"trak":
                self.tracks.append(self._track((a, b)))

    def _track(self, span):
        d = self.d
        tkhd = d[slice(*child(d, span, b"tkhd"))]
        tid = struct.unpack(">I", tkhd[12:16])[0]
        mdia = child(d, span, b"mdia")
        hdlr = d[slice(*child(d, mdia, b"hdlr"))]
        minf = child(d, mdia, b"minf")
        stbl = child(d, minf, b"stbl")
        stsd = d[slice(*child(d, stbl, b"stsd"))]
        stsz = d[slice(*child(d, stbl, b"stsz"))]
        fixed, n = struct.unpack(">II", stsz[4:12])
        sizes = list(struct.unpack(">%dI" % n, stsz[12:12 + 4 * n])) if not fixed else [fixed] * n
        stco = d[slice(*child(d, stbl, b"stco"))]
        k = struct.unpack(">I", stco[4:8])[0]
        offs = struct.unpack(">%dI" % k, stco[8:8 + 4 * k])
        stsc = d[slice(*child(d, stbl, b"stsc"))]
        m = struct.unpack(">I", stsc[4:8])[0]
        runs = [struct.unpack(">III", stsc[8 + 12 * i:20 + 12 * i]) for i in range(m)]
        samples, i = [], 0
        for ci, co in enumerate(offs):
            per = [p for f, p, _ in runs if f <= ci + 1][-1]
            o = co
            for _ in range(per):
                if i < n:
                    samples.append(d[o:o + sizes[i]])
                    o += sizes[i]
                    i += 1
        tref = {}
        tr = child(d, span, b"tref")
        if tr:
            for t, a, b in atoms(d, *tr):
                tref[t.decode()] = list(struct.unpack(">%dI" % ((b - a) // 4), d[a:b]))
        return {"id": tid, "type": hdlr[8:12].decode("latin1"), "codec": stsd[12:16].decode("latin1"),
                "samples": samples, "tref": tref}

    def track(self, tid):
        return next(t for t in self.tracks if t["id"] == tid)

    def first(self, kind):
        return next(t for t in self.tracks if t["type"] == kind)


# ---------- panoramas ----------

def pano_info(sample):
    """QTVRPanoSampleAtom ('pdat') -> view limits/defaults (degrees)."""
    p = qtfind(qtatoms(sample, 12, len(sample)), "pdat")["d"]
    imgref = struct.unpack(">I", p[4:8])[0]
    f = struct.unpack(">9f", p[12:48])
    sx, sy, nfx, nfy = struct.unpack(">IIHH", p[48:60])
    return imgref, {
        "pan": [f[0], f[1]], "tilt": [f[2], f[3]], "fov": [f[4], f[5]],
        "def": {"pan": f[6], "tilt": f[7], "fov": f[8]},
        # panorama is stored rotated 90 degrees: sx is the pano height, sy the pano width
        "width": sy, "height": sx, "tiles": nfy,
    }


def stitch(tiles, dest):
    """Stack the jpeg tile samples vertically, rotate clockwise to upright, write dest (jpg)."""
    tmp = OUT / "_tiles"
    tmp.mkdir(parents=True, exist_ok=True)
    ins, lab = [], ""
    for i, t in enumerate(tiles):
        p = tmp / f"t{i:02d}.jpg"
        p.write_bytes(t)
        ins += ["-i", str(p)]
        lab += f"[{i}:v]"
    fc = f"{lab}vstack=inputs={len(tiles)},transpose=1[v]"
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *ins, "-filter_complex", fc, "-map", "[v]",
                        "-frames:v", "1", "-q:v", "2", str(dest)], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed for {dest}: {r.stderr}")


def panoramas(movie, name, nodes, info):
    m = Movie(RAW / movie)
    pano = m.first("pano")
    imgt = pano["tref"]["imgt"]
    out = []
    for i, s in enumerate(pano["samples"][:nodes]):
        ref, meta = pano_info(s)
        tiles = m.track(imgt[ref - 1])["samples"]
        assert len(tiles) == meta["tiles"], (movie, i, len(tiles), meta["tiles"])
        file = f"{name}-{i + 1:02d}.jpg" if nodes > 1 else f"{name}.jpg"
        stitch(tiles, OUT / "pano" / file)
        meta["file"] = f"pano/{file}"
        out.append(meta)
    return m, out


# ---------- clockhands text ----------

STAMP = re.compile(r"\[(\d\d):(\d\d):(\d\d)\.\d\d\d\]")
RUN = re.compile(r"\{textColor: (\d+), (\d+), (\d+)\}")


def parse_hands(path):
    """-> list of 900 [line1, line2]; the red 'time-telling' letters are wrapped in {}."""
    txt = path.read_bytes().decode("mac_roman")
    body = txt[txt.index("[00:00:00"):]
    parts = STAMP.split(body)  # [pre, hh, mm, ss, text, hh, mm, ss, text, ...]
    entries = []
    for i in range(1, len(parts), 4):
        h, mi, s, t = int(parts[i]), int(parts[i + 1]), int(parts[i + 2]), parts[i + 3]
        if h:  # closing [01:00:00.000] stamp
            continue
        red = False

        def colour(mt):
            nonlocal red
            now = mt.group(1) == "65535" and mt.group(2) == "0"
            out = "{" if now and not red else ("}" if red and not now else "")
            red = now
            return out

        t = RUN.sub(colour, t)
        if red:
            t += "}"
        lines = [ln.strip() for ln in t.split("\r") if ln.strip()]
        assert len(lines) == 2, (path.name, mi, s, lines)
        entries.append((mi * 60 + s, lines))
    entries.sort()
    assert [e[0] for e in entries] == list(range(0, 3600, 4)), path.name
    return [e[1] for e in entries]


def main():
    (OUT / "pano").mkdir(parents=True, exist_ok=True)

    m, pauls = panoramas("pauls.mov", "pauls", 1, None)
    overlay = next(t for t in m.tracks if t["codec"].strip() == "png")
    (OUT / "pauls-overlay.png").write_bytes(overlay["samples"][0])
    _, whisper = panoramas("whisperscene.mov", "whisper", 24, None)
    _, scene = panoramas("clockscene.mov", "scene", 24, None)
    (OUT / "panos.json").write_text(json.dumps({"pauls": pauls[0], "whisper": whisper, "scene": scene}, indent=1))

    hands = [parse_hands(RAW / "hnds" / f"c{h:02d}hands.txt") for h in range(1, 25)]
    (OUT / "hands.json").write_text(json.dumps(hands, ensure_ascii=False, separators=(",", ":")))

    for f in (OUT / "_tiles").glob("*"):
        f.unlink()
    (OUT / "_tiles").rmdir()
    print("ok")


if __name__ == "__main__":
    main()
