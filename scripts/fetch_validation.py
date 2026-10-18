"""Small chronological holdout from HPWREN FIgLib, after the July 2022 model release."""
import argparse,csv,re
from pathlib import Path
import httpx
from urllib.parse import unquote,quote

SEQUENCE="20260909_GettyFire_wilson-w-mobo-c"
BASE="https://cdn.hpwren.ucsd.edu/HPWREN-FIgLib-Data/"+SEQUENCE+"/"
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sequence',default=SEQUENCE);args=parser.parse_args()
    if not re.fullmatch(r'[0-9]{8}_[A-Za-z0-9_-]+',args.sequence):raise ValueError('Invalid sequence identifier')
    sequence=args.sequence;base='https://cdn.hpwren.ucsd.edu/HPWREN-FIgLib-Data/'+sequence+'/'
    root=Path('data/validation')/sequence;root.mkdir(parents=True,exist_ok=True)
    html=httpx.get(base+'index.html',timeout=30).raise_for_status().text
    names=re.findall(r'href=([0-9]+_[+-][0-9]+\.jpg)',unquote(html))
    negative=[n for n in names if '_-' in n][::3]
    positive=[n for n in names if '_+' in n][::3]
    rows=[]
    with httpx.Client(timeout=30) as client:
        for name in negative+positive:
            file=root/name
            if not file.exists():file.write_bytes(client.get(base+quote(name)).raise_for_status().content)
            rows.append({'path':str(file),'label':int('_+' in name),'event':sequence,'offset_seconds':int(name.split('_')[1].split('.')[0])})
    if not negative or not positive:raise ValueError('Both negative and positive frames required')
    manifest=Path('data/validation/manifest.csv')
    with manifest.open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=['path','label','event','offset_seconds']);writer.writeheader();writer.writerows(rows)
    print(f'{len(rows)} held-out archive frames saved. Credit HPWREN / UCSD: https://www.hpwren.ucsd.edu/')

if __name__=='__main__':main()
