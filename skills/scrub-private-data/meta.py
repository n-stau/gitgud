"""Read and strip identifying metadata in files, detected by magic bytes (works on history blobs without a path).

Covers: JPEG/PNG/TIFF/HEIC EXIF (author, camera, serial, software, dates, GPS), PNG text chunks,
PDF info dictionary and XMP, Office/OpenDocument (creator, last editor, company, comment and revision authors).
Not covered: audio/video tags, PSD/RAW, metadata inside compressed PDF object streams.
"""
import io, re, struct, zipfile

MAX_XML = 20 * 1024 * 1024  # bytes read per Office XML part
MAX_OFFICE = 512 * 1024 * 1024  # total unpacked size an Office file may have to be rewritten

EXIF_TAGS = {0x010E: "ImageDescription", 0x010F: "Make", 0x0110: "Model", 0x0131: "Software", 0x0132: "DateTime",
             0x013B: "Artist", 0x8298: "Copyright", 0x9003: "DateTimeOriginal", 0xA430: "CameraOwnerName",
             0xA431: "BodySerialNumber", 0xA435: "LensSerialNumber", 0x9C9D: "XPAuthor", 0x9C9C: "XPComment"}
OFFICE_FIELDS = re.compile(rb"<(dc:creator|cp:lastModifiedBy|Company|Manager|meta:initial-creator|dc:title|cp:keywords)>([^<]+)<")
OFFICE_AUTHORS = re.compile(rb'\b(w:author|w:initials|author)="([^"]+)"')
PDF_KEYS = re.compile(rb"/(Author|Creator|Producer|Title|Subject|Keywords)\s*\(((?:[^()\\]|\\.)*)\)")
XMP_KEYS = re.compile(rb"<(dc:creator|xmp:CreatorTool|pdf:Producer|photoshop:AuthorsPosition|xmpRights:Owner)\b[^>]*>(.*?)</\1>", re.S)


def kind(b):
    if b[:3] == b"\xff\xd8\xff": return "jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n": return "png"
    if b[:4] in (b"II*\x00", b"MM\x00*"): return "tiff"
    if b[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"): return "heic"
    if b[:5] == b"%PDF-": return "pdf"
    if b[:4] == b"PK\x03\x04" and (b"docProps/" in b or b"meta.xml" in b): return "office"
    return None


def _tiff(b, t):
    """Parse IFD0 + Exif sub-IFD of a TIFF structure at offset t. Returns [(tag, value)], gps flag."""
    e = "<" if b[t:t + 2] == b"II" else ">"
    found, gps, seen = [], False, set()
    def ifd(off):
        nonlocal gps
        if off in seen or off + 2 > len(b): return
        seen.add(off)
        for k in range(struct.unpack(e + "H", b[off:off + 2])[0]):
            p = off + 2 + 12 * k
            tag, typ, cnt = struct.unpack(e + "HHI", b[p:p + 8])
            if tag == 0x8825: gps = True
            elif tag == 0x8769: ifd(t + struct.unpack(e + "I", b[p + 8:p + 12])[0])
            elif tag in EXIF_TAGS and typ in (1, 2, 7):
                v = b[p + 8:p + 8 + cnt] if cnt <= 4 else b[t + struct.unpack(e + "I", b[p + 8:p + 12])[0]:][:cnt]
                v = (v.decode("utf-16-le", "replace") if tag in (0x9C9D, 0x9C9C) else v.decode("utf-8", "replace")).strip("\x00 ")
                if v: found.append((EXIF_TAGS[tag], v))
    try:
        ifd(t + struct.unpack(e + "I", b[t + 4:t + 8])[0])
    except (struct.error, IndexError):
        pass
    return found, gps


def extract(b):
    """[(field, value)] of identifying metadata, plus ("GPS", "location") when present."""
    k, out = kind(b), []
    if k in ("jpeg", "tiff", "heic", "png"):
        i = b.find(b"Exif\x00\x00")
        t = i + 6 if i >= 0 else (0 if k == "tiff" else -1)
        if k == "png" and t < 0 and b"eXIf" in b:
            t = b.index(b"eXIf") + 4
        if t >= 0:
            f, gps = _tiff(b, t); out += f
            if gps: out.append(("GPS", "location"))
        if k == "png":  # walk chunks by length; tEXt = key\0value, iTXt = key\0flag method lang\0 key2\0 value
            i = 8
            while i + 8 <= len(b):
                n, typ = struct.unpack(">I", b[i:i + 4])[0], b[i + 4:i + 8]
                d = b[i + 8:i + 8 + n]
                if typ in (b"tEXt", b"iTXt") and b"\x00" in d:
                    key, val = d.split(b"\x00", 1)
                    if typ == b"iTXt":
                        val = val[2:].split(b"\x00", 2)[-1]
                    out.append((key.decode("latin-1"), val.decode("utf-8", "replace")[:300]))
                i += 12 + n
        if b"<x:xmpmeta" in b:
            out += [(m.group(1).decode(), re.sub(rb"<[^>]+>", b" ", m.group(2)).decode("utf-8", "replace").strip()) for m in XMP_KEYS.finditer(b)]
    elif k == "pdf":
        out += [(m.group(1).decode(), m.group(2).decode("latin-1")) for m in PDF_KEYS.finditer(b)]
        out += [(m.group(1).decode(), re.sub(rb"<[^>]+>", b" ", m.group(2)).decode("utf-8", "replace").strip()) for m in XMP_KEYS.finditer(b)]
    elif k == "office":
        try:
            z = zipfile.ZipFile(io.BytesIO(b))
            for n in z.namelist():
                if n.endswith(".xml") and (n.startswith(("docProps/", "word/", "xl/", "ppt/")) or n == "meta.xml"):
                    with z.open(n) as f:
                        x = f.read(MAX_XML)  # cap: a zip bomb must not exhaust memory
                    out += [(m.group(1).decode(), m.group(2).decode("utf-8", "replace")) for m in OFFICE_FIELDS.finditer(x)]
                    out += [(f"{n}:{m.group(1).decode()}", m.group(2).decode("utf-8", "replace")) for m in OFFICE_AUTHORS.finditer(x)]
        except zipfile.BadZipFile:
            pass
    return [(f, v.strip()) for f, v in dict.fromkeys(out) if v.strip()]


def strip(b):
    """Return b without identifying metadata, or None if the format is not handled / nothing to do."""
    k = kind(b)
    if k == "jpeg":
        out, i = bytearray(b[:2]), 2
        while i + 4 <= len(b) and b[i] == 0xFF and b[i + 1] not in (0xDA, 0xD9):
            n = struct.unpack(">H", b[i + 2:i + 4])[0]
            if b[i + 1] not in (0xE1, 0xED, 0xFE):  # APP1 EXIF/XMP, APP13 IPTC, COM
                out += b[i:i + 2 + n]
            i += 2 + n
        return bytes(out + b[i:])
    if k == "png":
        out, i = bytearray(b[:8]), 8
        while i + 8 <= len(b):
            n = struct.unpack(">I", b[i:i + 4])[0]
            if b[i + 4:i + 8] not in (b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"tIME"):
                out += b[i:i + 12 + n]
            i += 12 + n
        return bytes(out)
    if k == "pdf":  # same-length blanking keeps the xref table valid
        blank = lambda m: m.group(0)[:m.start(2) - m.start(0)] + b" " * len(m.group(2)) + m.group(0)[m.end(2) - m.start(0):]
        return XMP_KEYS.sub(blank, PDF_KEYS.sub(blank, b))
    if k == "office":
        src, dst = zipfile.ZipFile(io.BytesIO(b)), io.BytesIO()
        if sum(i.file_size for i in src.infolist()) > MAX_OFFICE:
            return None  # zip bomb or huge file: left untouched, scan.py still reports it
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
            for info in src.infolist():
                x = src.read(info)
                if info.filename.endswith(".xml"):
                    x = OFFICE_FIELDS.sub(lambda m: b"<" + m.group(1) + b"><", x)
                    x = OFFICE_AUTHORS.sub(lambda m: m.group(1) + b'="Author"', x)
                z.writestr(info, x)
        return dst.getvalue()
    return None
