from PIL import ExifTags, Image

from engine.photos import check_photos

HOUSE = (45.63, 27.80)


def jpeg_with_exif(path, date=None, gps=None, pattern=0):
    img = Image.new("RGB", (320, 240), (40, 90, 160))
    for x in range(0, 320, 16 + pattern):
        for y in range(0, 240, 3):
            img.putpixel((x, y), (255, 255, 255))
    exif = Image.Exif()
    if date:
        exif.get_ifd(ExifTags.IFD.Exif)[0x9003] = date
    if gps:
        lat, lon = gps
        exif.get_ifd(ExifTags.IFD.GPSInfo).update({1: "N", 2: (int(lat), (lat % 1) * 60, 0.0), 3: "E",
                                                   4: (int(lon), (lon % 1) * 60, 0.0)})
    img.save(path, "JPEG", exif=exif)
    return path


def test_photo_taken_before_the_event_is_flagged(tmp_path):
    p = jpeg_with_exif(tmp_path / "a.jpg", date="2024:09:01 10:00:00")
    result, findings = check_photos([p], "2024-09-14", None, [])
    assert [f.code for f in result.flags] == ["photo_before_event"]
    assert result.step == "photos"
    assert "a.jpg:exif_days_before_event" in [f.metric for f in findings]
    assert result.items[0].id == "a.jpg" and result.items[0].value == "2024-09-01"


def test_photo_far_from_the_house_is_flagged(tmp_path):
    p = jpeg_with_exif(tmp_path / "b.jpg", date="2024:09:14 10:00:00", gps=(45.657, 27.80))
    result, findings = check_photos([p], "2024-09-14", HOUSE, [])
    assert [f.code for f in result.flags] == ["photo_far_from_address"]
    km = [f.value for f in findings if f.metric == "b.jpg:exif_distance_to_address_km"][0]
    assert 2.5 < km < 3.5


def test_photo_near_the_house_and_no_house_are_fine(tmp_path):
    p = jpeg_with_exif(tmp_path / "c.jpg", date="2024:09:14 10:00:00", gps=(45.6305, 27.80))
    result, _ = check_photos([p], "2024-09-14", HOUSE, [])
    assert result.flags == [] and result.items[0].status == "ok"
    far = jpeg_with_exif(tmp_path / "d.jpg", date="2024:09:14 10:00:00", gps=(46.5, 27.80))
    result, findings = check_photos([far], "2024-09-14", None, [])
    assert result.flags == []
    assert not any("distance" in f.metric for f in findings)


def test_photo_without_date_is_flagged(tmp_path):
    p = jpeg_with_exif(tmp_path / "e.jpg")
    result, _ = check_photos([p], "2024-09-14", None, [])
    assert [f.code for f in result.flags] == ["photo_no_date"]
    assert result.items[0].value == "fără dată"


def test_copy_of_an_earlier_claim_photo_is_flagged(tmp_path):
    p = jpeg_with_exif(tmp_path / "f.jpg", date="2024:09:14 10:00:00")
    old = jpeg_with_exif(tmp_path / "old.jpg", date="2024:09:14 10:00:00")
    result, findings = check_photos([p], "2024-09-14", None, [old])
    assert [f.code for f in result.flags] == ["photo_copy_in_earlier_claim"]
    assert [f.value for f in findings if f.metric == "f.jpg:copy_in_other_claim"] == [True]


def test_unreadable_photo_is_a_flag_not_an_error(tmp_path):
    p = tmp_path / "g.jpg"
    p.write_text("not an image")
    result, findings = check_photos([p], "2024-09-14", None, [])
    assert [f.code for f in result.flags] == ["photo_unreadable"]
    assert [f.metric for f in findings] == ["g.jpg:unreadable"]


def test_no_photos_gives_one_info_item_and_no_flags():
    result, findings = check_photos([], "2024-09-14", None, [])
    assert result.flags == [] and findings == []
    assert [(i.status, i.label) for i in result.items] == [("info", "Nicio fotografie în dosar")]
