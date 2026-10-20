"""파일 변환 표와 작업 프로세스용 엔진. QWidget·DB·설정 접근 없음."""
import base64
from dataclasses import dataclass
import os
from pathlib import Path
import struct

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMarginsF, QRect, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QImageWriter, QPageLayout, QPageSize, QPainter, QPdfWriter

MAX_FILES = 100
MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_PDF_PAGES = 300
MAX_PAGE_PIXELS = 50_000_000


class FileConversionError(ValueError):
    """원본 경로·본문을 포함하지 않는 사용자용 오류."""


@dataclass(frozen=True)
class Kind:
    name: str
    extensions: tuple
    color: str
    background: str
    line: str
    targets: tuple


KINDS = {
    "image": Kind("사진", ("jpg", "jpeg", "png", "webp", "bmp"), "#0B6576", "#DDF1F4", "#5FA8B4",
                  ("jpg", "png", "webp", "bmp", "jpg_small", "ico", "pdf_bundle")),
    "pdf": Kind("PDF", ("pdf",), "#9A3412", "#FCEBDD", "#D08A5E", ("pdf_png", "pdf_jpg")),
    "hwp": Kind("한글", ("hwp",), "#1D4ED8", "#E6EEFD", "#7C9CF0", ("hwpx",)),
    "text": Kind("표·글", ("csv", "txt"), "#17673A", "#E3F3E8", "#6FB38A", ("utf8", "cp949")),
}


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    choices: tuple


QUALITY = Option("quality", "화질", (("보통(85)", 85), ("높게(95)", 95), ("낮게(70)", 70)))
LONG_EDGE = Option("long_edge", "긴 변", (("1920px", 1920), ("1280px", 1280), ("원래대로", 0)))
PNG_SIZE = Option("long_edge", "크기", (("원래대로", 0), ("1920px", 1920), ("1280px", 1280)))
PAPER = Option("paper", "용지", (("A4 세로", "portrait"), ("A4 가로", "landscape"), ("사진 크기대로", "image")))
MARGIN = Option("margin", "여백", (("좁게", 8), ("없음", 0), ("보통", 15)))
RESOLUTION = Option("dpi", "해상도", (("보통(150dpi)", 150), ("높게(300dpi)", 300)))


@dataclass(frozen=True)
class Target:
    name: str
    tag: str
    description: str
    button: str
    options: tuple
    extension: str
    naming: str = "extension"


TARGETS = {
    "jpg_small": Target("작은 JPG", "가볍게 보내기", "메일·메신저에 알맞아요", "작은 JPG로 바꾸기", (LONG_EDGE, QUALITY), "jpg", "small"),
    "jpg": Target("JPG", "사진에 알맞게", "용량과 화질의 균형이 좋아요", "JPG로 바꾸기", (QUALITY,), "jpg"),
    "png": Target("PNG", "또렷하게", "글자·도표가 선명해요. 용량은 커져요", "PNG로 바꾸기", (PNG_SIZE,), "png"),
    "webp": Target("WEBP", "가장 작게", "오래된 프로그램은 못 열 수 있어요", "WEBP로 바꾸기", (QUALITY,), "webp"),
    "bmp": Target("BMP", "압축 없이", "압축하지 않아 용량이 아주 커요", "BMP로 바꾸기", (), "bmp"),
    "ico": Target("ICO", "아이콘", "16 · 32 · 48 · 256px을 한 파일에", "ICO로 바꾸기", (), "ico"),
    "pdf_bundle": Target("PDF", "문서로 제출", "사진 한 장이면 한 쪽, 여러 장이면 넣은 순서대로 한 파일", "PDF로 묶기",
                         (PAPER, MARGIN), "pdf", "bundle"),
    "pdf_png": Target("PNG", "쪽마다 한 장", "새 폴더에 쪽 번호 순서로 저장해요", "PNG로 바꾸기", (RESOLUTION,), "png", "pages"),
    "pdf_jpg": Target("JPG", "쪽마다 한 장", "새 폴더에 쪽 번호 순서로 저장해요", "JPG로 바꾸기", (RESOLUTION,), "jpg", "pages"),
    "hwpx": Target("HWPX", "개방형 한글 문서", "표·그림·수식 배치는 열어서 확인해 주세요", "HWPX로 바꾸기", (), "hwpx"),
    "utf8": Target("UTF-8", "엑셀·웹에서 안 깨지게", "지금 EUC-KR로 저장된 파일이에요", "UTF-8로 바꾸기", (), "", "encoding"),
    "cp949": Target("EUC-KR", "예전 프로그램용", "표현할 수 없는 글자가 있으면 바꾸지 않아요", "EUC-KR로 바꾸기", (), "", "encoding"),
}


def kind_for(path):
    extension = Path(path).suffix.lower().lstrip(".")
    return next((key for key, kind in KINDS.items() if extension in kind.extensions), None)


def source_format(path):
    extension = Path(path).suffix.lower().lstrip(".")
    return "jpg" if extension == "jpeg" else extension


def file_filter():
    return "지원하는 파일 (" + " ".join(f"*.{ext}" for kind in KINDS.values() for ext in kind.extensions) + ")"


def recommend(kind, source_formats):
    formats = set(source_formats)
    if kind == "image":
        source = next(iter(formats)) if len(formats) == 1 else "mixed"
        first = {
            "jpg": ["jpg_small", "png", "pdf_bundle"],
            "png": ["jpg", "jpg_small", "pdf_bundle"],
            "webp": ["jpg", "png", "pdf_bundle"],
            "bmp": ["jpg", "png", "pdf_bundle"],
        }.get(source, ["jpg_small", "png", "pdf_bundle"])
        others = [key for key in ("jpg", "jpg_small", "png", "webp", "bmp", "ico")
                  if key not in first and key != source]
        return first, others
    if kind == "text":
        # 여러 인코딩이면 첫 파일의 반대쪽을 추천하고 같은 인코딩은 건너뛴다.
        first = next(iter(source_formats), "utf8")
        return (["cp949"] if first == "utf8" else ["utf8"]), []
    return list(KINDS[kind].targets), []


def relation_groups():
    """관계도도 실제 지원 표에서 파생한다."""
    groups = []
    for kind_id, kind in KINDS.items():
        if kind_id == "image":
            formats = " · ".join(TARGETS[key].name for key in kind.targets if key in ("jpg", "png", "webp", "bmp"))
            rows = [(formats, "서로"), (TARGETS["jpg_small"].name, "크기·용량 줄이기"),
                    (TARGETS["ico"].name, TARGETS["ico"].tag), (TARGETS["pdf_bundle"].name, "여러 장을 한 파일로")]
        else:
            rows = [(TARGETS[key].name, TARGETS[key].tag) for key in kind.targets]
        groups.append((kind_id, rows))
    return groups


def settings_for(target_id, supplied=None):
    supplied = supplied or {}
    result = {}
    for option in TARGETS[target_id].options:
        value = supplied.get(option.key, option.choices[0][1])
        if value not in [choice[1] for choice in option.choices]:
            raise FileConversionError("변환 설정을 확인해 주세요")
        result[option.key] = value
    return result


def check_source(path):
    path = Path(path)
    if not kind_for(path) or not path.is_file():
        raise FileConversionError("지원하지 않는 형식이에요")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise FileConversionError("100 MB 이하 파일만 바꿀 수 있어요")
    return path


def read_text(path):
    with open(path, "rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise FileConversionError("100 MB 이하 파일만 바꿀 수 있어요")
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig", errors="strict"), "utf8"
        except UnicodeError as exc:
            raise FileConversionError("글자 인코딩을 알 수 없어요") from exc
    for encoding, format_id in (("utf-8", "utf8"), ("cp949", "cp949")):
        try:
            return raw.decode(encoding, errors="strict"), format_id
        except UnicodeError:
            continue  # 다음 strict 코덱도 실패하면 판정 오류로 보고한다.
    raise FileConversionError("글자 인코딩을 알 수 없어요")


def image_reader(path):
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    actual = bytes(reader.format()).decode("ascii", errors="replace")
    if actual not in KINDS["image"].extensions:
        raise FileConversionError("사진을 읽을 수 없어요(손상)")
    size = reader.size()
    # 축소 미리보기도 원본에 같은 할당 한도를 적용한다. Qt 전역값은 바꾸지 않는다.
    if size.width() * size.height() * 4 > QImageReader.allocationLimit() * 1024 * 1024:
        raise FileConversionError("사진이 너무 커서 열 수 없어요")
    return reader


def read_image(path):
    image = image_reader(path).read()
    if image.isNull():
        raise FileConversionError("사진을 읽을 수 없어요(손상)")
    return image


def clean_image(image, opaque=False):
    """픽셀만 새 표면으로 그려 EXIF·위치·텍스트 메타데이터를 전달하지 않는다."""
    result = QImage(image.size(), QImage.Format_RGB32 if opaque else QImage.Format_ARGB32)
    if result.isNull():
        raise FileConversionError("사진이 너무 커서 열 수 없어요")
    result.fill(Qt.white if opaque else Qt.transparent)
    painter = QPainter(result)
    painter.drawImage(0, 0, image)
    painter.end()
    return result


def shrink(image, long_edge):
    if long_edge and max(image.width(), image.height()) > long_edge:
        return image.scaled(long_edge, long_edge, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return image


def png_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise FileConversionError("사진을 저장할 수 없어요")
    buffer.close()
    return bytes(data)


def write_image(image, output, extension, quality=85):
    writer = QImageWriter(str(output), extension.encode("ascii"))
    if extension in ("jpg", "webp"):
        writer.setQuality(quality)
    if not writer.write(image):
        raise FileConversionError("저장 폴더에 쓸 수 없어요")
    check = QImageReader(str(output))
    if not check.canRead() or check.size() != image.size():
        raise FileConversionError("변환 결과를 확인할 수 없어요")


def write_ico(image, output):
    # Qt ico writer는 한 크기만 쓴다. ICONDIR + PNG 4항목을 직접 묶는다.
    frames = []
    for size in (16, 32, 48, 256):
        square = QImage(size, size, QImage.Format_ARGB32)
        square.fill(Qt.transparent)
        scaled = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter = QPainter(square)
        painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        painter.end()
        frames.append((size, png_bytes(square)))
    offset = 6 + 16 * len(frames)
    with open(output, "xb") as stream:
        stream.write(struct.pack("<HHH", 0, 1, len(frames)))
        for size, payload in frames:
            stream.write(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(payload), offset))
            offset += len(payload)
        for _, payload in frames:
            stream.write(payload)
    reader = QImageReader(str(output), b"ico")
    if reader.imageCount() != 4 or reader.read().isNull():
        raise FileConversionError("변환 결과를 확인할 수 없어요")


def pdf_reader(path):
    reader = QImageReader(str(path), b"pdf")
    count = reader.imageCount()
    if not reader.canRead() or count <= 0:
        raise FileConversionError("열 수 없는 PDF예요(암호·손상)")
    if count > MAX_PDF_PAGES:
        raise FileConversionError("쪽이 너무 많아요(300쪽까지)")
    return reader, count


def inspect_source(path):
    """UI용 판독도 격리 프로세스에서 한다. 미리보기는 새 PNG 픽셀만 전달."""
    path = check_source(path)
    kind = kind_for(path)
    result = {"bytes": path.stat().st_size, "format": source_format(path)}
    if kind == "image":
        image = read_image(path)
        result.update(width=image.width(), height=image.height(),
                      preview=base64.b64encode(png_bytes(clean_image(shrink(image, 240)))).decode("ascii"))
    elif kind == "text":
        _, result["format"] = read_text(path)
    elif kind == "pdf":
        _, result["pages"] = pdf_reader(path)
    return result


def write_pdf(sources, output, settings, progress):
    writer = QPdfWriter(str(output))
    writer.setResolution(300)
    writer.setCreator("기후노트")
    painter = QPainter()
    try:
        for index, source in enumerate(sources):
            image = clean_image(read_image(source), opaque=True)
            paper = settings["paper"]
            margin = settings["margin"]
            if paper == "image":
                width, height = image.width()*72/300, image.height()*72/300
                # 사진 비율의 쪽에 여백을 확보한다. 아주 작은 사진도 양쪽 여백이
                # 본문 전체를 삼켜 빈 PDF가 되지 않으며 원래 픽셀을 키울 필요가 없다.
                factor = 1 + (2*margin*72/25.4) / min(width, height)
                page = QPageSize(QSizeF(width*factor, height*factor), QPageSize.Point, "", QPageSize.ExactMatch)
            else:
                page = QPageSize(QPageSize.A4)
            orientation = QPageLayout.Landscape if paper == "landscape" else QPageLayout.Portrait
            layout = QPageLayout(page, orientation, QMarginsF(margin, margin, margin, margin), QPageLayout.Millimeter)
            if not writer.setPageLayout(layout):
                raise FileConversionError("용지 크기와 여백을 확인해 주세요")
            if index == 0:
                if not painter.begin(writer):
                    raise FileConversionError("저장 폴더에 쓸 수 없어요")
            elif not writer.newPage():
                raise FileConversionError("저장 폴더에 쓸 수 없어요")
            size = image.size().scaled(writer.width(), writer.height(), Qt.KeepAspectRatio)
            painter.drawImage(QRect((writer.width()-size.width())//2, (writer.height()-size.height())//2,
                                    size.width(), size.height()), image)
            progress()
    finally:
        if painter.isActive():
            painter.end()
    del writer  # PDF의 끝을 기록한 뒤 검사한다.
    _, count = pdf_reader(output)
    if count != len(sources):
        raise FileConversionError("변환 결과를 확인할 수 없어요")


def output_name(sources, target_id):
    source = Path(sources[0])
    target = TARGETS[target_id]
    if target.naming == "pages":
        return source.stem + "_쪽별"
    if target.naming == "encoding":
        return source.stem + "_" + target.name + source.suffix
    stem = source.stem
    if target.naming == "small":
        stem += " (작게)"
    if target.naming == "bundle" and len(sources) > 1:
        stem += "_묶음"
    return stem + "." + target.extension


def convert_item(sources, target_id, supplied, stage, progress=lambda: None):
    sources = [check_source(source) for source in sources]
    if not sources or len(sources) > MAX_FILES or target_id not in TARGETS:
        raise FileConversionError("지원하지 않는 형식이에요")
    if len(sources) != 1 and target_id != "pdf_bundle":
        raise FileConversionError("지원하지 않는 형식이에요")
    if any(target_id not in KINDS[kind_for(source)].targets for source in sources):
        raise FileConversionError("지원하지 않는 형식이에요")
    settings = settings_for(target_id, supplied)
    target = TARGETS[target_id]
    stage = Path(stage)
    output = stage / ("result" if target.naming == "pages" else "result." + (target.extension or sources[0].suffix.lstrip(".")))
    source = sources[0]
    if target_id == "pdf_bundle":
        write_pdf(sources, output, settings, progress)
    elif kind_for(source) == "image":
        if source_format(source) == target_id:
            return {"ok": True, "skipped": True, "message": f"이미 {target.name}예요"}
        image = clean_image(shrink(read_image(source), settings.get("long_edge", 0)), target_id in ("jpg", "jpg_small", "bmp"))
        if target_id == "ico":
            write_ico(image, output)
        else:
            write_image(image, output, target.extension, settings.get("quality", 85))
    elif target.naming == "pages":
        reader, count = pdf_reader(source)
        output.mkdir()
        for index in range(count):
            if index and not reader.jumpToImage(index):
                raise FileConversionError("열 수 없는 PDF예요(암호·손상)")
            # qpdf의 size는 72dpi 포인트 크기다.
            size = reader.size()
            scaled = QSize(round(size.width() * settings["dpi"] / 72), round(size.height() * settings["dpi"] / 72))
            if scaled.width() * scaled.height() > MAX_PAGE_PIXELS:
                raise FileConversionError("쪽이 너무 커요(쪽당 50MP까지)")
            reader.setScaledSize(scaled)
            image = reader.read()
            if image.isNull():
                raise FileConversionError("열 수 없는 PDF예요(암호·손상)")
            write_image(clean_image(image, target_id == "pdf_jpg"), output / f"{source.stem}_{index+1:03d}.{target.extension}", target.extension)
            progress()
    elif kind_for(source) == "text":
        text, encoding = read_text(source)
        if encoding == target_id:
            return {"ok": True, "skipped": True, "message": f"이미 {target.name}예요"}
        try:
            payload = text.encode("utf-8-sig" if target_id == "utf8" else "cp949", errors="strict")
        except UnicodeError as exc:
            raise FileConversionError("EUC-KR로 나타낼 수 없는 글자가 있어요") from exc
        with open(output, "xb") as stream:
            stream.write(payload)
        with open(output, "rb") as stream:
            if stream.read() != payload:
                raise FileConversionError("변환 결과를 확인할 수 없어요")
    else:
        raise FileConversionError("지원하지 않는 형식이에요")
    result = {"ok": True, "message": "완료", "artifact": output.name,
              "file_count": count if target.naming == "pages" else 1}
    if kind_for(source) == "image" and target_id != "pdf_bundle":
        rendered = QImageReader(str(output)).read()
        if rendered.isNull():
            raise FileConversionError("변환 결과를 확인할 수 없어요")
        result["preview"] = base64.b64encode(png_bytes(clean_image(shrink(rendered, 240)))).decode("ascii")
        result["size"] = f"{rendered.width()} × {rendered.height()}"
    return result


def publish_output(staged, directory, name, is_directory=False):
    """Windows rename은 기존 파일/폴더가 생긴 경합에서도 덮어쓰지 않는다."""
    staged, directory = Path(staged), Path(directory)
    stem, suffix = (name, "") if is_directory else (Path(name).stem, Path(name).suffix)
    for number in range(10000):
        candidate = directory / (stem + (f" ({number})" if number else "") + suffix)
        try:
            # POSIX 테스트에서도 기존 결과를 보호하고 Windows가 최종 경합을 막는다.
            if candidate.exists():
                continue
            os.rename(staged, candidate)
            return candidate
        except FileExistsError:
            continue
    raise FileConversionError("같은 이름의 결과가 너무 많아요")
