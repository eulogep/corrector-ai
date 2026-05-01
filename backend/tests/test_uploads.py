"""
Tests pour la validation des fichiers uploadés.
Vérifie taille, MIME type, et magic bytes.
"""

import pytest
import io
import struct
import zlib
from unittest.mock import AsyncMock, MagicMock
from backend.services.utils import validate_upload, _detect_mime
from fastapi import HTTPException


def _make_png(w=2, h=2):
    """Generate minimal valid PNG bytes."""
    sig = b'\x89PNG\r\n\x1a\n'
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    ihdr = chunk(b'IHDR', struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    raw = b''
    for y in range(h):
        raw += b'\x00' + b'\xff\xff\xff' * w
    idat = chunk(b'IDAT', zlib.compress(raw))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


def _make_jpeg():
    """Generate minimal JPEG header bytes."""
    return b'\xff\xd8\xff\xe0' + b'\x00' * 100


def _make_pdf():
    """Generate minimal PDF header bytes."""
    return b'%PDF-1.4 ' + b'\x00' * 100


def _make_fake_upload(content: bytes, filename: str, content_type: str):
    """Create a mock UploadFile."""
    mock = AsyncMock()
    mock.read = AsyncMock(return_value=content)
    mock.filename = filename
    mock.content_type = content_type
    return mock


# ━━━ Tests de détection magic bytes ━━━

def test_detect_png():
    assert _detect_mime(_make_png()) == "image/png"

def test_detect_jpeg():
    assert _detect_mime(_make_jpeg()) == "image/jpeg"

def test_detect_pdf():
    assert _detect_mime(_make_pdf()) == "application/pdf"

def test_detect_unknown():
    assert _detect_mime(b'\x00\x00\x00\x00') is None

def test_detect_text():
    assert _detect_mime(b'Hello world this is text') is None


# ━━━ Tests de validate_upload ━━━

@pytest.mark.asyncio
async def test_valid_png_upload():
    """PNG valide → retourne le contenu."""
    png = _make_png()
    file = _make_fake_upload(png, "test.png", "image/png")
    result = await validate_upload(file)
    assert result == png


@pytest.mark.asyncio
async def test_valid_jpeg_upload():
    """JPEG valide → retourne le contenu."""
    jpeg = _make_jpeg()
    file = _make_fake_upload(jpeg, "photo.jpg", "image/jpeg")
    result = await validate_upload(file)
    assert result == jpeg


@pytest.mark.asyncio
async def test_reject_oversized_file():
    """Fichier > 10 MB → 413."""
    big = b'\xff\xd8\xff\xe0' + b'\x00' * (11 * 1024 * 1024)
    file = _make_fake_upload(big, "huge.jpg", "image/jpeg")
    with pytest.raises(HTTPException) as exc:
        await validate_upload(file)
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_reject_bad_mime_type():
    """MIME déclaré non supporté → 415."""
    png = _make_png()
    file = _make_fake_upload(png, "evil.exe", "application/octet-stream")
    with pytest.raises(HTTPException) as exc:
        await validate_upload(file)
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_reject_fake_extension():
    """Fichier texte renommé en .png → 415 (magic bytes invalides)."""
    fake = b'This is not a real image file'
    file = _make_fake_upload(fake, "fake.png", "image/png")
    with pytest.raises(HTTPException) as exc:
        await validate_upload(file)
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_valid_pdf_upload():
    """PDF valide → retourne le contenu."""
    pdf = _make_pdf()
    file = _make_fake_upload(pdf, "doc.pdf", "application/pdf")
    result = await validate_upload(file)
    assert result == pdf
