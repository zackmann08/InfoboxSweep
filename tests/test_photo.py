"""Does an article have a photograph of its subject?"""

import pytest

from infoboxsweep.photo import FileInfo, LeadImage, not_a_photo, photo_verdict

JPEG = FileInfo('image/jpeg', 3000, 2000)


def test_a_free_jpeg_lead_image_is_a_photograph():
    found = photo_verdict(LeadImage('File:Ohio Statehouse.jpg', True), JPEG)
    assert found.found and found.review is None
    assert found.evidence == 'lead image [[:File:Ohio Statehouse.jpg]] (JPEG, 3000×2000)'
    assert found.shown == '[[:File:Ohio Statehouse.jpg]]'
    for mime in ('image/tiff', 'image/webp', 'image/heif'):
        assert photo_verdict(LeadImage('File:X.img', True), FileInfo(mime, 800, 600)).found


def test_no_lead_image():
    found = photo_verdict(None, None)
    assert not found.found and found.review is None and found.evidence == 'no lead image'


@pytest.mark.parametrize(('file', 'info', 'why'), [
    ('File:Ohio in United States.svg', FileInfo('image/svg+xml', 1000, 800), 'is SVG+XML'),
    ('File:Ohio County locator map.png', FileInfo('image/png', 800, 600), 'has "locator"'),
    ('File:Flag of Ohio.jpg', JPEG, 'has "flag"'),
    ('File:Coat of arms of Ohio.jpg', JPEG, 'has "coat of arms"'),
    ('File:Acme_Corp_logo.jpg', JPEG, 'has "logo"'),
    ('File:John Doe signature.jpg', JPEG, 'has "signature"'),
    ('File:Replace this image male.jpg', JPEG, 'has "replace this image"'),
    ('File:Commons-logo.svg', FileInfo('image/svg+xml', 12, 16), 'has "logo"'),
    ('File:Tiny thing.jpg', FileInfo('image/jpeg', 120, 90), 'an icon'),
    ('File:Clip.webm', FileInfo('video/webm', 1920, 1080), 'is WEBM'),
])
def test_not_a_photograph(file, info, why):
    found = photo_verdict(LeadImage(file, True), info)
    assert not found.found and found.review is None
    assert why in found.evidence


@pytest.mark.parametrize(('lead', 'info', 'why'), [
    (LeadImage('File:Building.png', True), FileInfo('image/png', 1200, 900),
     'is a PNG: is it a photograph'),
    (LeadImage('File:Old photo.gif', True), FileInfo('image/gif', 400, 300), 'is a GIF'),
    (LeadImage('File:John Doe 2010.jpg', False), JPEG, 'is non-free'),
    (LeadImage('File:Deleted.jpg', True), None, 'could not be found'),
])
def test_left_for_a_human(lead, info, why):
    found = photo_verdict(lead, info)
    assert not found.found and why in found.review


def test_words_not_parts_of_words():
    assert not_a_photo('File:Mapperley Park.jpg') is None   # "map" in "Mapperley"
    assert not_a_photo('File:Seattle skyline.jpg') is None
    assert not_a_photo('File:Map of Ohio.jpg') == 'its name has "map"'
