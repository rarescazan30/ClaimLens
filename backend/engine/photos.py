"""Photo check step: EXIF date and GPS, and the same image in earlier claims (perceptual hash).

Local only, no network. The findings are the ones the photo forensics agent reports for its local checks, so the
step can run early and the agent can reuse its result.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import imagehash
from PIL import ExifTags, Image

from engine.geo import haversine_m
from engine.models import CheckItem, Finding, Flag, StepResult

HASH_DISTANCE = 6
FAR_FROM_ADDRESS_KM = 1


def _dms(value) -> float:
    d, m, s = (float(x) for x in value)
    return d + m / 60 + s / 3600


def read_exif(img: Image.Image) -> tuple[date | None, tuple[float, float] | None]:
    exif = img.getexif()
    raw = exif.get_ifd(ExifTags.IFD.Exif).get(0x9003) or exif.get(0x0132)
    taken = None
    if raw:
        try:
            taken = datetime.strptime(str(raw)[:19], "%Y:%m:%d %H:%M:%S").date()
        except ValueError:
            pass
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    where = None
    try:
        if gps.get(2) and gps.get(4):
            lat, lon = _dms(gps[2]), _dms(gps[4])
            where = (-lat if gps.get(1) == "S" else lat, -lon if gps.get(3) == "W" else lon)
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return taken, where


def image_hash(path):
    try:
        with Image.open(path) as im:
            return imagehash.phash(im)
    except Exception:
        return None


def check_photos(paths: list[Path], event_date: str, house: tuple[float, float] | None,
                 earlier: list[Path]) -> tuple[StepResult, list[Finding]]:
    event = date.fromisoformat(str(event_date)[:10])
    findings: list[Finding] = []
    items: list[CheckItem] = []
    flags: list[Flag] = []
    other_hashes = [h for h in map(image_hash, earlier) if h is not None]

    def f(name, check, value, source, unit=None, url=None):
        findings.append(Finding(metric=f"{name}:{check}", value=value, unit=unit, source=source, url=url))

    if not paths:
        items.append(CheckItem(id="photos", label="Nicio fotografie în dosar", status="info"))
        return StepResult(step="photos", items=items, flags=flags), findings

    for path in paths:
        name = Path(path).name
        notes: list[str] = []
        photo_flags: list[Flag] = []

        def flag(code, reason):
            notes.append(reason)
            photo_flags.append(Flag(step="photos", code=code, field=name, severity="warn", reason=reason))

        try:
            with Image.open(path) as img:
                img.load()
                taken, where = read_exif(img)
                digest = imagehash.phash(img)
        except Exception:
            f(name, "unreadable", True, "Fișier")
            flag("photo_unreadable", f"{name} nu a putut fi citită ca imagine.")
            items.append(CheckItem(id=name, label=name, value="fără dată", status="flag", reason=" ".join(notes)))
            flags.extend(photo_flags)
            continue
        if taken is None and where is None:
            f(name, "exif_missing", True, "EXIF")
        if taken is not None:
            f(name, "exif_date", taken.isoformat(), "EXIF")
            days = (event - taken).days
            f(name, "exif_days_before_event" if days >= 0 else "exif_days_after_event", abs(days), "EXIF", "zile")
            if days > 0:
                flag("photo_before_event", f"Fotografia {name} a fost făcută cu {days} zile înainte de eveniment.")
        else:
            flag("photo_no_date", f"Fotografia {name} nu are dată de captură în metadate.")
        if where is not None:
            km = round(haversine_m(house[0], house[1], *where) / 1000, 2) if house else None
            if km is not None:
                f(name, "exif_distance_to_address_km", km, "EXIF", "km")
                if km > FAR_FROM_ADDRESS_KM:
                    flag("photo_far_from_address", f"Fotografia {name} a fost făcută la {km} km de adresa daunei.")
        copy = any(digest - h <= HASH_DISTANCE for h in other_hashes)
        f(name, "copy_in_other_claim", copy, "Comparare cu fotografiile din alte dosare")
        if copy:
            flag("photo_copy_in_earlier_claim", f"Fotografia {name} apare și într-un dosar anterior.")
        items.append(CheckItem(id=name, label=name, value=taken.isoformat() if taken else "fără dată",
                               status="flag" if photo_flags else "ok", reason=" ".join(notes) or None))
        flags.extend(photo_flags)
    return StepResult(step="photos", items=items, flags=flags), findings
