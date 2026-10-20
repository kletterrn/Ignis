"""Use content versions so shared assets update on GitHub Pages and locally."""
import hashlib
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'static'


def asset_url(filename, prefix='/static/'):
    version = hashlib.sha256((STATIC / filename).read_bytes()).hexdigest()[:12]
    return f'{prefix}{filename}?v={version}'
