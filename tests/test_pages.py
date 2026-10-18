import json
import subprocess
import sys
from pathlib import Path


def test_github_pages_uses_relative_assets_and_public_api_without_operator():
    subprocess.run([sys.executable,'-m','scripts.prepare_site','--github-pages'],check=True)
    html=Path('outputs/github-pages/index.html').read_text(encoding='utf-8')
    assert './static/app.js' in html and 'id="operator-console"' not in html
    assert '"operator": false' in html and '"csrf": null' in html
    assert 'https://ignis-fire-monitoring.davidkhaliqi05.chatgpt.site' in html
    assert 'href="./"' in html
