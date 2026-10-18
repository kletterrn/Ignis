"""Copy only Site sources/build output to a separate ignored publishing checkout."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'data'/'site-publish'
target.parent.mkdir(parents=True,exist_ok=True)
shutil.copytree(ROOT/'site',target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('node_modules','.git','.env*','.dev.vars','.wrangler','.sites-runtime','.vinext','*.log'))
assert not list(target.rglob('.dev.vars')) and not list(target.rglob('.env'))
print('Sanitized publishing checkout: '+str(target))
