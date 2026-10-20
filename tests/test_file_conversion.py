"""합성 픽셀·PDF·문자열만으로 변환 결과와 원본 보존을 확인한다."""
import struct
from pathlib import Path

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPdfWriter, QPageSize

import file_conversion as fc


@pytest.fixture(autouse=True)
def gui(qapp):
    yield


def image_file(path, width=80, height=40):
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.fillRect(0, 0, width//2, height, QColor("#0B7285"))
    painter.end()
    image.setText("private", "location metadata")
    assert image.save(str(path))
    return path


def convert(tmp_path, sources, target, settings=None):
    stage = tmp_path / ("stage_" + target)
    stage.mkdir(exist_ok=True)
    result = fc.convert_item(sources, target, settings or {}, stage)
    return result, stage / result.get("artifact", "none")


@pytest.mark.parametrize("target", ["jpg", "jpg_small", "webp", "bmp", "ico"])
def test_image_conversion_pixels_alpha_metadata_and_source(tmp_path, target):
    source = image_file(tmp_path / "photo.png")
    before = source.read_bytes()
    result, output = convert(tmp_path, [source], target)
    assert result["ok"] and result["preview"]
    assert source.read_bytes() == before
    image = QImage(str(output))
    assert not image.isNull()
    # ICO reader가 생성하는 내부 깊이 표식은 입력 EXIF/텍스트 메타데이터가 아니다.
    assert set(image.textKeys()) <= {"_q_icoOrigDepth"}
    if target in ("jpg", "jpg_small", "bmp"):
        color = image.pixelColor(70, 20)
        assert min(color.red(), color.green(), color.blue()) > 245
    if target == "ico":
        raw = output.read_bytes()
        assert struct.unpack("<HHH", raw[:6]) == (0, 1, 4)
        for index, size in enumerate((16, 32, 48, 256)):
            width, height, _, _, planes, bits, length, offset = struct.unpack("<BBBBHHII", raw[6+index*16:22+index*16])
            assert width == height == size % 256 and (planes, bits) == (1, 32)
            frame = QImage.fromData(raw[offset:offset+length], "PNG")
            assert frame.size() == QSize(size, size)
            assert frame.pixelColor(0, 0).alpha() == 0


def test_resize_does_not_enlarge_and_png_roundtrip(tmp_path):
    source = image_file(tmp_path / "photo.bmp", 2400, 1200)
    _, output = convert(tmp_path, [source], "png", {"long_edge": 1280})
    assert QImage(str(output)).size() == QSize(1280, 640)
    small = image_file(tmp_path / "small.png", 80, 40)
    _, output = convert(tmp_path, [small], "jpg_small")
    assert QImage(str(output)).size() == QSize(80, 40)


def test_jpeg_exif_orientation_applied_and_removed(tmp_path):
    source = image_file(tmp_path / "rotated.jpg", 80, 40)
    raw = source.read_bytes()
    # little-endian TIFF IFD: orientation=6 (90° clockwise)
    tiff = b"II" + struct.pack("<HIH", 42, 8, 1) + struct.pack("<HHIHHI", 0x112, 3, 1, 6, 0, 0)
    exif = b"Exif\0\0" + tiff
    source.write_bytes(raw[:2] + b"\xff\xe1" + struct.pack(">H", len(exif)+2) + exif + raw[2:])
    before = source.read_bytes()
    _, output = convert(tmp_path, [source], "png")
    assert QImage(str(output)).size() == QSize(40, 80)
    assert source.read_bytes() == before
    assert b"Exif" not in output.read_bytes()


def two_page_pdf(path):
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.A4))
    painter = QPainter(writer)
    painter.fillRect(0, 0, 200, 200, Qt.red)
    assert writer.newPage()
    painter.fillRect(0, 0, 200, 200, Qt.blue)
    painter.end()
    del writer
    return path


@pytest.mark.parametrize("target", ["pdf_png", "pdf_jpg"])
def test_pdf_pages_and_resolution(tmp_path, target):
    source = two_page_pdf(tmp_path / "two.pdf")
    before = source.read_bytes()
    _, output = convert(tmp_path, [source], target)
    pages = sorted(output.iterdir())
    assert len(pages) == 2
    assert pages[0].name == "two_001." + fc.TARGETS[target].extension
    assert QImage(str(pages[0])).size() == QImage(str(pages[1])).size()
    assert abs(QImage(str(pages[0])).width()-1240) <= 3  # A4 / 72 * 150
    assert source.read_bytes() == before


@pytest.mark.parametrize("paper", ["portrait", "landscape", "image"])
def test_three_photos_make_one_three_page_pdf(tmp_path, paper):
    sources = [image_file(tmp_path / f"img{i}.png", 900, 600) for i in range(3)]
    _, output = convert(tmp_path, sources, "pdf_bundle", {"paper": paper})
    reader, count = fc.pdf_reader(output)
    assert count == 3 and not reader.read().isNull()


@pytest.mark.parametrize("margin", [0, 8, 15])
def test_tiny_photo_pdf_keeps_ratio_and_visible_pixels(tmp_path, margin):
    source = image_file(tmp_path / "tiny.png", 80, 40)
    _, output = convert(tmp_path, [source], "pdf_bundle", {"paper": "image", "margin": margin})
    reader, _ = fc.pdf_reader(output)
    size = reader.size()
    assert abs(size.width()/size.height()-2) < .15  # 정수 pt 반올림 허용
    reader.setScaledSize(QSize(400, 200))
    rendered = reader.read()
    assert any(rendered.pixelColor(x, y).red() < 80 for x in range(400) for y in range(200))


def test_text_roundtrip_bom_newlines_and_strict_failure(tmp_path):
    text = "이름,값\r\n기후,3\n마지막\r"
    source = tmp_path / "표.csv"
    source.write_bytes(text.encode("cp949"))
    _, utf = convert(tmp_path, [source], "utf8")
    assert utf.read_bytes() == b"\xef\xbb\xbf"+text.encode()
    _, output = convert(tmp_path, [utf], "cp949")
    assert output.read_bytes() == source.read_bytes()
    source.write_bytes("한글😀".encode())
    with pytest.raises(fc.FileConversionError, match="나타낼 수 없는"):
        convert(tmp_path, [source], "cp949")
    source.write_bytes(b"\xff\x80")
    with pytest.raises(fc.FileConversionError, match="인코딩"):
        fc.inspect_source(source)


def test_same_format_is_skipped(tmp_path):
    source = image_file(tmp_path / "same.png")
    result, _ = convert(tmp_path, [source], "png")
    assert result["skipped"] and result["message"] == "이미 PNG예요"
    assert list((tmp_path / "stage_png").iterdir()) == []


def test_publish_file_folder_conflicts_and_names(tmp_path):
    existing = tmp_path / "a.png"
    existing.write_bytes(b"old")
    staged = tmp_path / "new"
    staged.write_bytes(b"new")
    output = fc.publish_output(staged, tmp_path, "a.png")
    assert output.name == "a (1).png" and existing.read_bytes() == b"old"
    (tmp_path / "a_쪽별").mkdir()
    folder = tmp_path / "new_folder"
    folder.mkdir()
    (folder / "a_001.png").write_bytes(b"pixels")
    assert fc.publish_output(folder, tmp_path, "a_쪽별", True).name == "a_쪽별 (1)"
    assert fc.output_name([Path("a.jpg"), Path("b.jpg")], "pdf_bundle") == "a_묶음.pdf"
    assert fc.output_name([Path("a.CSV")], "utf8") == "a_UTF-8.CSV"


def test_limits_corruption_and_kind_mismatch(tmp_path, monkeypatch):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not pdf")
    with pytest.raises(fc.FileConversionError, match="열 수 없는 PDF"):
        convert(tmp_path, [bad], "pdf_png")
    source = two_page_pdf(tmp_path / "two.pdf")
    monkeypatch.setattr(fc, "MAX_PDF_PAGES", 1)
    with pytest.raises(fc.FileConversionError, match="쪽이 너무"):
        convert(tmp_path, [source], "pdf_jpg")
    monkeypatch.setattr(fc, "MAX_PDF_PAGES", 300)
    monkeypatch.setattr(fc, "MAX_PAGE_PIXELS", 10)
    with pytest.raises(fc.FileConversionError, match="쪽이 너무 커"):
        convert(tmp_path, [source], "pdf_jpg")
    monkeypatch.setattr(fc, "MAX_SOURCE_BYTES", 10)
    with pytest.raises(fc.FileConversionError, match="100 MB"):
        fc.inspect_source(source)


@pytest.mark.parametrize("formats,recs,others", [
    (["jpg"], ["jpg_small", "png", "pdf_bundle"], ["webp", "bmp", "ico"]),
    (["png"], ["jpg", "jpg_small", "pdf_bundle"], ["webp", "bmp", "ico"]),
    (["webp"], ["jpg", "png", "pdf_bundle"], ["jpg_small", "bmp", "ico"]),
    (["bmp"], ["jpg", "png", "pdf_bundle"], ["jpg_small", "webp", "ico"]),
    (["jpg", "png"], ["jpg_small", "png", "pdf_bundle"], ["jpg", "webp", "bmp", "ico"]),
])
def test_recommendations(formats, recs, others):
    assert fc.recommend("image", formats) == (recs, others)
