"""Provision runtime values from stdin without printing credentials."""
import argparse,json,os,subprocess,sys,base64
from pathlib import Path
import httpx

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--github',action='store_true');args=parser.parse_args()
    import getpass
    values=json.loads(getpass.getpass('Runtime JSON (hidden): ') if sys.stdin.isatty() else sys.stdin.readline())
    root=Path(__file__).resolve().parents[1]
    lines=(root/'.env').read_text().splitlines() if (root/'.env').exists() else []
    lines=[line for line in lines if line.split('=',1)[0] not in values]
    (root/'.env').write_text('\n'.join(lines+[key+'='+value for key,value in values.items()])+'\n',encoding='utf-8')
    (root/'site'/'.dev.vars').write_text('\n'.join(key+'='+values[key] for key in ('IGNIS_COLLECTOR_TOKEN','IGNIS_OPERATOR_TOKEN'))+'\n',encoding='utf-8')
    if args.github:
        from nacl.public import PublicKey,SealedBox
        response=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,check=True,env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never'))
        credential=dict(line.split('=',1) for line in response.stdout.splitlines() if '=' in line)
        with httpx.Client(base_url='https://api.github.com/repos/kletterrn/Ignis',headers={'Authorization':'Bearer '+credential['password'],'Accept':'application/vnd.github+json'},timeout=30) as client:
            key=client.get('/actions/secrets/public-key').raise_for_status().json()
            encrypted=SealedBox(PublicKey(base64.b64decode(key['key']))).encrypt(values['IGNIS_COLLECTOR_TOKEN'].encode())
            client.put('/actions/secrets/IGNIS_COLLECTOR_TOKEN',json={'encrypted_value':base64.b64encode(encrypted).decode(),'key_id':key['key_id']}).raise_for_status()
            variable=client.get('/actions/variables/IGNIS_SITE_URL')
            if variable.status_code==404:client.post('/actions/variables',json={'name':'IGNIS_SITE_URL','value':values['IGNIS_SITE_URL']}).raise_for_status()
            else:client.patch('/actions/variables/IGNIS_SITE_URL',json={'name':'IGNIS_SITE_URL','value':values['IGNIS_SITE_URL']}).raise_for_status()
        print('GitHub collector secret and site URL configured. FIRMS remains unconfigured.')
    print('Local runtime configured; secret values omitted.')

if __name__=='__main__':main()
