# Contributing to Ignis

Ignis is an open-source public fire-analysis field pilot. Contributions are welcome
through GitHub issues and pull requests. By contributing, you license your changes
under the repository's Apache-2.0 license. Include provenance and permission for
any third-party code or data you add.

## Reproduce locally

Follow the Windows instructions in README.md, then run:

```powershell
uv sync --frozen
uv run pytest -q
node --test tests/*.test.cjs
uv run python -m scripts.prepare_site
Set-Location site
npm ci --no-audit --no-fund
npx tsc --noEmit
npm run build
```

Edit `static/` and `templates/` for shared dashboard changes, then regenerate
`site/public/`. Do not edit generated public assets independently. Cloud API code
is under `site/lib/`; local processing is under `services/` and `providers/`.
Never commit `.env`, tokens, camera URLs, raw footage, downloaded weights or
private evidence. Never send fixture incidents to the production Site.

Include a regression check for changed behavior and separate demonstrated checks
from field claims. Camera scores are not calibrated probabilities; hotspots are
not confirmed fires; wind is not measured fire movement. Preserve that distinction.
Do not add area, height or location measurements without valid georeferencing and
provenance. Report model performance on independent data, including false alerts.

## Security reports

Never disclose credentials, private imagery or exploitable details in public
issues. Use GitHub's private vulnerability-reporting facility when available;
otherwise request a private reporting channel from the maintainer without posting
the vulnerability details. Revoke exposed provider keys at their provider.
