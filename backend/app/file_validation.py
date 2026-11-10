"""Sanitize untrusted files in a disposable, time-bounded parser process.

The worker has no database connection, shell, network calls, or filesystem output.
These format checks are defense in depth, not a substitute for malware scanning.
"""
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import sysconfig
import threading
import unicodedata
import warnings

MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 16000000
MAX_PAGES = 100
MAX_OBJECTS = 20000
VALIDATORS = threading.BoundedSemaphore(2)
MIMES = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'GIF': 'image/gif', 'WEBP': 'image/webp'}
EXTENSIONS = {'application/pdf': {'.pdf'}, 'image/png': {'.png'}, 'image/jpeg': {'.jpg', '.jpeg'}, 'image/gif': {'.gif'}, 'image/webp': {'.webp'}}


def safe_filename(filename, extension):
    name = unicodedata.normalize('NFKC', PurePosixPath(filename.replace('\\', '/')).name)
    if ':' in name or any(unicodedata.category(char).startswith('C') for char in name):
        raise ValueError('The filename contains unsupported characters.')
    stem = re.sub(r'[^\w ()-]', '_', PurePosixPath(name).stem).strip(' ._')[:140] or 'attachment'
    return f'{stem}{extension}'


def sanitize_file(filename, declared_type, payload):
    from PIL import Image
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import IndirectObject

    if not payload or len(payload) > MAX_BYTES:
        raise ValueError('Choose a nonempty file of 2 MB or smaller.')
    suffix = PurePosixPath(filename.replace('\\', '/')).suffix.lower()
    if declared_type not in EXTENSIONS or suffix not in EXTENSIONS[declared_type]:
        raise ValueError('Use a PDF, PNG, JPEG, GIF, or WebP file with a matching extension.')
    output = BytesIO()
    if declared_type == 'application/pdf':
        if not payload.startswith(b'%PDF-'):
            raise ValueError('The file is not a valid PDF.')
        reader = PdfReader(BytesIO(payload), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ValueError('Use an unencrypted PDF with 1–100 pages.')
        forbidden = {'/JavaScript', '/JS', '/OpenAction', '/AA', '/Launch', '/RichMedia', '/EmbeddedFiles',
                     '/EmbeddedFile', '/Filespec', '/XFA', '/SubmitForm', '/GoToR', '/GoToE', '/URI', '/AcroForm'}
        pending = [(reader.trailer, 0)]
        visited = set()
        count = 0
        while pending:
            value, depth = pending.pop()
            count += 1
            if count > MAX_OBJECTS or depth > 50:
                raise ValueError('This PDF is too complex. Upload a flattened copy.')
            if isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in visited:
                    continue
                visited.add(key)
                value = value.get_object()
            if isinstance(value, dict):
                if forbidden.intersection(value):
                    raise ValueError('PDF actions, links, forms and embedded files are not supported. Upload a flattened copy.')
                pending.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, (list, tuple)):
                pending.extend((child, depth + 1) for child in value)
        writer = PdfWriter()
        for page in reader.pages:
            page.pop('/Metadata', None)
            writer.add_page(page)
        writer.add_metadata({})
        writer.write(output)
        content_type, extension = 'application/pdf', '.pdf'
    else:
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as original:
                if MIMES.get(original.format) != declared_type or original.width * original.height > MAX_PIXELS:
                    raise ValueError('Use a matching image format up to 16 megapixels.')
                original.seek(0)
                original.load()  # Decode pixels, rather than trusting only a header.
                alpha = 'A' in original.getbands() or 'transparency' in original.info
                image = original.convert('RGBA' if alpha else 'RGB')
                image.info.clear()
                if original.format == 'JPEG':
                    image.convert('RGB').save(output, format='JPEG', quality=92)
                    content_type, extension = 'image/jpeg', '.jpg'
                elif original.format == 'WEBP':
                    image.save(output, format='WEBP', lossless=True)
                    content_type, extension = 'image/webp', '.webp'
                else:
                    # A single sanitized frame also removes GIF animation payloads.
                    image.save(output, format='PNG', optimize=True)
                    content_type, extension = 'image/png', '.png'
    canonical = output.getvalue()
    if not canonical or len(canonical) > MAX_BYTES:
        raise ValueError('The sanitized file exceeds 2 MB. Reduce its dimensions or file size.')
    return safe_filename(filename, extension), content_type, canonical


def validate_isolated(filename, declared_type, payload):
    from fastapi import HTTPException
    if len(payload) > MAX_BYTES:
        raise HTTPException(413, 'Attachments must be 2 MB or smaller.')
    if not VALIDATORS.acquire(blocking=False):
        raise HTTPException(429, 'File validation is busy. Please try again shortly.')
    try:
        envelope = json.dumps({'filename': filename[:300], 'content_type': declared_type[:80]}).encode() + b'\n' + payload
        # Bypass Windows' venv redirector: killing only that launcher on timeout
        # can leave its real parser child running. Run the base interpreter
        # directly, isolated from environment/user-site modules, with only our
        # known venv packages added. No customer input becomes Python/shell code.
        bootstrap = f"import sys,runpy;sys.path.insert(0,{sysconfig.get_path('purelib')!r});runpy.run_path({str(Path(__file__).resolve())!r},run_name='__main__')"
        executable = getattr(sys, '_base_executable', sys.executable)
        result = subprocess.run([executable, '-I', '-S', '-c', bootstrap], input=envelope,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)  # nosec B603
        header, _, canonical = result.stdout.partition(b'\n')
        metadata = json.loads(header)
        if result.returncode != 0 or 'error' in metadata or not canonical or len(canonical) > MAX_BYTES:
            raise HTTPException(422, metadata.get('error', 'File validation failed. Upload a simpler file.'))
        return metadata['filename'], metadata['content_type'], canonical
    except subprocess.TimeoutExpired as failure:
        raise HTTPException(422, 'File validation timed out. Upload a simpler or flattened file.') from failure
    except (ValueError, KeyError) as failure:
        raise HTTPException(422, 'File validation failed. Upload a simpler file.') from failure
    finally:
        VALIDATORS.release()


if __name__ == '__main__':
    try:
        metadata = json.loads(sys.stdin.buffer.readline(4096))
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
        name, mime, safe = sanitize_file(metadata['filename'], metadata['content_type'], data)
        sys.stdout.buffer.write(json.dumps({'filename': name, 'content_type': mime}).encode() + b'\n' + safe)
    except ValueError as error:
        sys.stdout.buffer.write(json.dumps({'error': str(error)[:250]}).encode() + b'\n')
        sys.exit(1)
    except Exception:
        sys.stdout.buffer.write(b'{"error":"The file is damaged or unsupported. Upload a valid PDF or image."}\n')
        sys.exit(1)
