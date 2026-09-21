#!/usr/bin/env python3
import argparse, hashlib, json, zipfile
from datetime import datetime, timezone
from pathlib import Path

APP_ID='eve-jump-planner'
FORMAT=2
# Internal EXE name remains legacy-compatible so v3.4.3 can apply this update.
EXE_NAME='EVE Jump Planner.exe'

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def read_version(root):
    return (root/'VERSION').read_text(encoding='utf-8').strip()

def main():
    ap=argparse.ArgumentParser(description='Create New Eden Command .ejpupdate package')
    ap.add_argument('--root',default='.',help='project root')
    ap.add_argument('--mode',choices=['frozen-onedir','source'],required=True)
    ap.add_argument('--app-dir',help='path to packaged onedir application folder')
    ap.add_argument('--output-dir',default='releases')
    args=ap.parse_args()
    root=Path(args.root).resolve()
    version=read_version(root)
    outdir=(root/args.output_dir).resolve() if not Path(args.output_dir).is_absolute() else Path(args.output_dir)
    outdir.mkdir(parents=True,exist_ok=True)
    package=outdir/f'New_Eden_Command_Update_v{version}.ejpupdate'

    inputs=[]
    if args.mode=='frozen-onedir':
        if not args.app_dir: ap.error('--app-dir is required for frozen-onedir mode')
        app_dir=Path(args.app_dir).resolve()
        exe=app_dir/EXE_NAME
        if not exe.exists(): raise SystemExit(f'EXE not found: {exe}')
        for path in sorted(p for p in app_dir.rglob('*') if p.is_file()):
            inputs.append((path.relative_to(app_dir).as_posix(),path))
    else:
        for name in ('app.py','VERSION','README.md','run.bat'):
            path=root/name
            if path.exists(): inputs.append((name,path))

    if not inputs:
        raise SystemExit('No update payload files were found.')

    files=[]
    for rel,path in inputs:
        files.append({'path':rel.replace('\\','/'),'size':path.stat().st_size,'sha256':sha256(path)})
    manifest={
        'format':FORMAT,
        'app_id':APP_ID,
        'version':version,
        'mode':args.mode,
        'channel':'stable',
        'created_utc':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
        'files':files,
    }
    with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        z.writestr('manifest.json',json.dumps(manifest,indent=2,sort_keys=True)+'\n')
        for rel,path in inputs:
            z.write(path,'payload/'+rel.replace('\\','/'))
    print(package)
    print('FILES',len(files))
    print('SHA256',sha256(package))

if __name__=='__main__': main()
