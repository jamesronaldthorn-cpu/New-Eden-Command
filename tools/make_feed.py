#!/usr/bin/env python3
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

APP_ID='eve-jump-planner'

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(description='Create latest.json update feed for New Eden Command')
    ap.add_argument('--root',default='.')
    ap.add_argument('--installer',required=True)
    ap.add_argument('--update',required=True)
    ap.add_argument('--output',default='releases/latest.json')
    args=ap.parse_args()
    root=Path(args.root).resolve()
    version=(root/'VERSION').read_text(encoding='utf-8').strip()
    installer=Path(args.installer).resolve(); update=Path(args.update).resolve()
    if not installer.exists() or not update.exists(): raise SystemExit('Installer or update file is missing.')
    data={
        'format':1,
        'app_id':APP_ID,
        'channel':'stable',
        'version':version,
        'created_utc':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
        'update_url':update.name,
        'update_size':update.stat().st_size,
        'update_sha256':sha256(update),
        'installer_url':installer.name,
        'installer_size':installer.stat().st_size,
        'installer_sha256':sha256(installer),
    }
    out=Path(args.output)
    if not out.is_absolute(): out=root/out
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(out)

if __name__=='__main__': main()
