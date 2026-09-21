import json, math, sqlite3, threading, urllib.request, urllib.parse, urllib.error, zipfile, tempfile, os, time, sys, subprocess, shutil, csv, base64, hashlib, secrets, webbrowser, http.server, concurrent.futures
from datetime import datetime, timezone, timedelta
from collections import deque
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# Keep the Windows UI crisp on high-DPI displays before Tk creates a window.
if os.name=='nt':
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try: ctypes.windll.user32.SetProcessDPIAware()
        except Exception: pass

APP_NAME='New Eden Command'
VERSION='3.4.6'
SDE_SCHEMA_VERSION=8
APP_ID='eve-jump-planner'
UPDATE_FORMAT=2
UPDATE_EXTENSION='.ejpupdate'
APP_EXECUTABLE_NAME='EVE Jump Planner.exe'
LY_METERS=9.46e15
BASE=Path.home()/'.eve_jump_planner'
DATA=BASE/'data'; DATA.mkdir(parents=True, exist_ok=True)
DB=DATA/'eve.db'; META=DATA/'meta.json'; CONFIG=BASE/'config.json'; ASSET_PRICE_CACHE=DATA/'asset_market_prices.json'; APP_DIR=Path(__file__).resolve().parent; BACKUPS=BASE/'backups'; DOWNLOADS=BASE/'downloads'
LATEST='https://developers.eveonline.com/static-data/tranquility/latest.jsonl'
SDE_URL='https://developers.eveonline.com/static-data/tranquility/eve-online-static-data-{build}-jsonl.zip'
ESI_BASE='https://esi.evetech.net'
THE_FORGE_REGION_ID=10000002
JITA_44_STATION_ID=60003760
MARKET_CACHE_SECONDS=300
ASSET_PRICE_CACHE_SECONDS=3600
LIVE_RULES_CACHE_SECONDS=300
HIGHSEC_THRESHOLD=0.45
SSO_WELL_KNOWN='https://login.eveonline.com/.well-known/oauth-authorization-server'
SSO_VERIFY='https://login.eveonline.com/v2/oauth/verify'
ESI_SKILLS_SCOPE='esi-skills.read_skills.v1'
ESI_WAYPOINT_SCOPE='esi-ui.write_waypoint.v1'
ESI_OPEN_WINDOW_SCOPE='esi-ui.open_window.v1'
ESI_LOCATION_SCOPE='esi-location.read_location.v1'
ESI_SHIP_SCOPE='esi-location.read_ship_type.v1'
ESI_ONLINE_SCOPE='esi-location.read_online.v1'
ESI_ASSETS_SCOPE='esi-assets.read_assets.v1'
ESI_CONTRACTS_SCOPE='esi-contracts.read_character_contracts.v1'
ESI_INDUSTRY_SCOPE='esi-industry.read_character_jobs.v1'
ESI_WALLET_SCOPE='esi-wallet.read_character_wallet.v1'
ESI_SKILLQUEUE_SCOPE='esi-skills.read_skillqueue.v1'
ESI_CLONES_SCOPE='esi-clones.read_clones.v1'
ESI_STRUCTURES_SCOPE='esi-universe.read_structures.v1'
ESI_REQUESTED_SCOPES=(
    ESI_SKILLS_SCOPE,ESI_WAYPOINT_SCOPE,ESI_OPEN_WINDOW_SCOPE,
    ESI_LOCATION_SCOPE,ESI_SHIP_SCOPE,ESI_ONLINE_SCOPE,ESI_ASSETS_SCOPE,
    ESI_CONTRACTS_SCOPE,ESI_INDUSTRY_SCOPE,ESI_WALLET_SCOPE,
    ESI_SKILLQUEUE_SCOPE,ESI_CLONES_SCOPE,ESI_STRUCTURES_SCOPE,
)
ESI_SCOPE_STRING=' '.join(ESI_REQUESTED_SCOPES)
DEFAULT_SSO_REDIRECT='http://127.0.0.1:8765/callback'


CONTRACT_TYPE_NAMES={
    'courier':'Courier','item_exchange':'Item Exchange','auction':'Auction','unknown':'Other Contract',
}
CONTRACT_STATUS_NAMES={
    'outstanding':'Outstanding','in_progress':'In Progress','finished':'Finished',
    'finished_issuer':'Finished — Issuer','finished_contractor':'Finished — Contractor',
    'cancelled':'Cancelled','rejected':'Rejected','failed':'Failed','deleted':'Deleted','reversed':'Reversed',
}
CONTRACT_AVAILABILITY_NAMES={'public':'Public','personal':'Personal','corporation':'Corporation','alliance':'Alliance'}
INDUSTRY_ACTIVITY_NAMES={0:'None',1:'Manufacturing',3:'Time Efficiency Research',4:'Material Efficiency Research',5:'Copying',7:'Reverse Engineering',8:'Invention',9:'Reactions',11:'Reactions'}

def contract_type_name(value):
    key=str(value or '').strip().lower(); return CONTRACT_TYPE_NAMES.get(key, key.replace('_',' ').title() if key else 'Contract')

def contract_status_name(value):
    key=str(value or '').strip().lower(); return CONTRACT_STATUS_NAMES.get(key, key.replace('_',' ').title() if key else 'Unknown')

def contract_status_bucket(value):
    key=str(value or '').strip().lower()
    if key=='outstanding': return 'outstanding'
    if key=='in_progress': return 'in_progress'
    return 'finished'

def industry_activity_name(value):
    try:key=int(value)
    except Exception:return 'Industry Activity'
    return INDUSTRY_ACTIVITY_NAMES.get(key,'Industry Activity')

def load_embedded_sso_settings():
    """Load public EVE SSO app settings bundled by the release build.

    A desktop PKCE Client ID is a public identifier, not a secret. The build
    bundles it so end users never need to see or enter developer settings.
    No client secret is bundled or supported.
    """
    candidates=[]
    if getattr(sys,'frozen',False) and hasattr(sys,'_MEIPASS'):
        candidates.append(Path(sys._MEIPASS)/'_eve_sso.json')
    candidates.append(APP_DIR/'developer_settings.local.json')
    for path in candidates:
        try:
            data=json.loads(path.read_text(encoding='utf-8-sig'))
            if isinstance(data,dict):
                cid=str(data.get('eve_sso_client_id','')).strip()
                redirect=str(data.get('eve_sso_redirect_uri') or DEFAULT_SSO_REDIRECT).strip()
                if cid:
                    return {'client_id':cid,'redirect_uri':redirect}
        except Exception:
            pass
    return {'client_id':'','redirect_uri':DEFAULT_SSO_REDIRECT}

SSO_BUILD_SETTINGS=load_embedded_sso_settings()
APP_SSO_CLIENT_ID=str(SSO_BUILD_SETTINGS.get('client_id','')).strip()
APP_SSO_REDIRECT_URI=str(SSO_BUILD_SETTINGS.get('redirect_uri') or DEFAULT_SSO_REDIRECT).strip()

def bundled_asset(relative):
    base=Path(sys._MEIPASS) if getattr(sys,'frozen',False) and hasattr(sys,'_MEIPASS') else APP_DIR
    return base/relative

def migrate_windows_branding_shortcuts():
    """Rename legacy per-user shortcuts after an in-app branding update.

    v3.4.3 can install v3.4.4 through the onedir updater, which replaces the
    runtime but does not run Inno Setup. Renaming an existing .lnk preserves its
    target and automatically picks up the new executable icon. The full Setup
    installer performs the same cleanup when it is used instead.
    """
    if os.name!='nt': return
    candidates=[]
    appdata=os.environ.get('APPDATA')
    if appdata:
        candidates.append(Path(appdata)/'Microsoft'/'Windows'/'Start Menu'/'Programs')
    for env_name in ('USERPROFILE','OneDrive','OneDriveConsumer'):
        base=os.environ.get(env_name)
        if base: candidates.append(Path(base)/'Desktop')
    seen=set()
    for folder in candidates:
        try:
            key=str(folder.resolve()).casefold()
        except Exception:
            key=str(folder).casefold()
        if key in seen: continue
        seen.add(key)
        old=folder/'EVE Jump Planner.lnk'; new=folder/f'{APP_NAME}.lnk'
        try:
            if old.exists():
                folder.mkdir(parents=True,exist_ok=True)
                if new.exists(): old.unlink(missing_ok=True)
                else: old.replace(new)
        except Exception:
            pass

CHARACTER_SKILLS={
    'Jump Drive Calibration':21611,
    'Jump Fuel Conservation':21610,
    'Jump Freighters':29029,
}

ISOTOPES={
 'Amarr':'Helium Isotopes','Caldari':'Nitrogen Isotopes','Gallente':'Oxygen Isotopes',
 'Minmatar':'Hydrogen Isotopes','ORE':'Oxygen Isotopes','CONCORD':'Helium Isotopes',
}
ISOTOPE_TYPE_IDS={
 'Helium Isotopes':16274,
 'Oxygen Isotopes':17887,
 'Nitrogen Isotopes':17888,
 'Hydrogen Isotopes':17889,
}

SHIPS={
 # Jump Freighters
 'Ark':      {'class':'Jump Freighter','faction':'Amarr','range':5.0,'fuel':8800,'isotope':'Helium Isotopes','jf_bonus':True,'fuel_bay_m3':12000},
 'Rhea':     {'class':'Jump Freighter','faction':'Caldari','range':5.0,'fuel':10000,'isotope':'Nitrogen Isotopes','jf_bonus':True,'fuel_bay_m3':12000},
 'Anshar':   {'class':'Jump Freighter','faction':'Gallente','range':5.0,'fuel':9400,'isotope':'Oxygen Isotopes','jf_bonus':True,'fuel_bay_m3':12000},
 'Nomad':    {'class':'Jump Freighter','faction':'Minmatar','range':5.0,'fuel':8200,'isotope':'Hydrogen Isotopes','jf_bonus':True,'fuel_bay_m3':12000},

 # Black Ops
 'Redeemer': {'class':'Black Ops','faction':'Amarr','range':4.0,'fuel':700,'isotope':'Helium Isotopes','fuel_bay_m3':2150},
 'Widow':    {'class':'Black Ops','faction':'Caldari','range':4.0,'fuel':700,'isotope':'Nitrogen Isotopes','fuel_bay_m3':2150},
 'Sin':      {'class':'Black Ops','faction':'Gallente','range':4.0,'fuel':700,'isotope':'Oxygen Isotopes','fuel_bay_m3':2150},
 'Panther':  {'class':'Black Ops','faction':'Minmatar','range':4.0,'fuel':700,'isotope':'Hydrogen Isotopes','fuel_bay_m3':2150},
 'Marshal':  {'class':'Black Ops','faction':'CONCORD','range':4.0,'fuel':700,'isotope':'Helium Isotopes','fuel_bay_m3':2150},

 # Capital Industrial
 'Rorqual':  {'class':'Capital Industrial','faction':'ORE','range':5.0,'fuel':4000,'isotope':'Oxygen Isotopes','fuel_bay_m3':10000},

 # Dreadnoughts
 'Revelation': {'class':'Dreadnought','faction':'Amarr','range':3.5,'fuel':3000,'isotope':'Helium Isotopes','fuel_bay_m3':8000},
 'Phoenix':    {'class':'Dreadnought','faction':'Caldari','range':3.5,'fuel':3000,'isotope':'Nitrogen Isotopes','fuel_bay_m3':8000},
 'Moros':      {'class':'Dreadnought','faction':'Gallente','range':3.5,'fuel':3000,'isotope':'Oxygen Isotopes','fuel_bay_m3':8000},
 'Naglfar':    {'class':'Dreadnought','faction':'Minmatar','range':3.5,'fuel':3000,'isotope':'Hydrogen Isotopes','fuel_bay_m3':8000},

 # Carriers
 'Archon':     {'class':'Carrier','faction':'Amarr','range':3.5,'fuel':3000,'isotope':'Helium Isotopes','fuel_bay_m3':3000},
 'Chimera':    {'class':'Carrier','faction':'Caldari','range':3.5,'fuel':3000,'isotope':'Nitrogen Isotopes','fuel_bay_m3':3000},
 'Thanatos':   {'class':'Carrier','faction':'Gallente','range':3.5,'fuel':3000,'isotope':'Oxygen Isotopes','fuel_bay_m3':3000},
 'Nidhoggur':  {'class':'Carrier','faction':'Minmatar','range':3.5,'fuel':3000,'isotope':'Hydrogen Isotopes','fuel_bay_m3':3000},

 # Force Auxiliaries
 'Apostle':    {'class':'Force Auxiliary','faction':'Amarr','range':3.5,'fuel':3000,'isotope':'Helium Isotopes','fuel_bay_m3':6000},
 'Minokawa':   {'class':'Force Auxiliary','faction':'Caldari','range':3.5,'fuel':3000,'isotope':'Nitrogen Isotopes','fuel_bay_m3':6000},
 'Ninazu':     {'class':'Force Auxiliary','faction':'Gallente','range':3.5,'fuel':3000,'isotope':'Oxygen Isotopes','fuel_bay_m3':6000},
 'Lif':        {'class':'Force Auxiliary','faction':'Minmatar','range':3.5,'fuel':3000,'isotope':'Hydrogen Isotopes','fuel_bay_m3':6000},

 # Command Carriers
 'Salvation':  {'class':'Command Carrier','faction':'Amarr','range':3.75,'fuel':3000,'isotope':'Helium Isotopes','fuel_bay_m3':7500},
 'Simurgh':    {'class':'Command Carrier','faction':'Caldari','range':3.75,'fuel':3000,'isotope':'Nitrogen Isotopes','fuel_bay_m3':7500},
 'Gaia':       {'class':'Command Carrier','faction':'Gallente','range':3.75,'fuel':3000,'isotope':'Oxygen Isotopes','fuel_bay_m3':7500},
 'Ymir':       {'class':'Command Carrier','faction':'Minmatar','range':3.75,'fuel':3000,'isotope':'Hydrogen Isotopes','fuel_bay_m3':7500},

 # Lancer Dreadnoughts
 'Bane':       {'class':'Lancer Dreadnought','faction':'Amarr','range':4.0,'fuel':3000,'isotope':'Helium Isotopes','fuel_bay_m3':20000},
 'Karura':     {'class':'Lancer Dreadnought','faction':'Caldari','range':4.0,'fuel':3000,'isotope':'Nitrogen Isotopes','fuel_bay_m3':20000},
 'Hubris':     {'class':'Lancer Dreadnought','faction':'Gallente','range':4.0,'fuel':3000,'isotope':'Oxygen Isotopes','fuel_bay_m3':20000},
 'Valravn':    {'class':'Lancer Dreadnought','faction':'Minmatar','range':4.0,'fuel':3000,'isotope':'Hydrogen Isotopes','fuel_bay_m3':20000},

 # Supercarriers
 'Aeon':       {'class':'Supercarrier','faction':'Amarr','range':3.0,'fuel':3000,'isotope':'Helium Isotopes','fuel_bay_m3':5000},
 'Wyvern':     {'class':'Supercarrier','faction':'Caldari','range':3.0,'fuel':3000,'isotope':'Nitrogen Isotopes','fuel_bay_m3':5000},
 'Nyx':        {'class':'Supercarrier','faction':'Gallente','range':3.0,'fuel':3000,'isotope':'Oxygen Isotopes','fuel_bay_m3':5000},
 'Hel':        {'class':'Supercarrier','faction':'Minmatar','range':3.0,'fuel':3000,'isotope':'Hydrogen Isotopes','fuel_bay_m3':5000},

 # Titans
 'Avatar':     {'class':'Titan','faction':'Amarr','range':3.0,'fuel':3000,'isotope':'Helium Isotopes','fuel_bay_m3':60000},
 'Leviathan':  {'class':'Titan','faction':'Caldari','range':3.0,'fuel':3000,'isotope':'Nitrogen Isotopes','fuel_bay_m3':60000},
 'Erebus':     {'class':'Titan','faction':'Gallente','range':3.0,'fuel':3000,'isotope':'Oxygen Isotopes','fuel_bay_m3':60000},
 'Ragnarok':   {'class':'Titan','faction':'Minmatar','range':3.0,'fuel':3000,'isotope':'Hydrogen Isotopes','fuel_bay_m3':60000},
}

# v1.1.0 and earlier used generic class/race labels for several capital ships.
# Keep old saved profiles/routes working by translating those labels to the real hull names.
LEGACY_SHIP_NAMES={
 'Dreadnought — Amarr':'Revelation', 'Dreadnought — Caldari':'Phoenix', 'Dreadnought — Gallente':'Moros', 'Dreadnought — Minmatar':'Naglfar',
 'Carrier — Amarr':'Archon', 'Carrier — Caldari':'Chimera', 'Carrier — Gallente':'Thanatos', 'Carrier — Minmatar':'Nidhoggur',
 'Force Auxiliary — Amarr':'Apostle', 'Force Auxiliary — Caldari':'Minokawa', 'Force Auxiliary — Gallente':'Ninazu', 'Force Auxiliary — Minmatar':'Lif',
 'Command Carrier — Amarr':'Salvation', 'Command Carrier — Caldari':'Simurgh', 'Command Carrier — Gallente':'Gaia', 'Command Carrier — Minmatar':'Ymir',
 'Lancer Dreadnought — Amarr':'Bane', 'Lancer Dreadnought — Caldari':'Karura', 'Lancer Dreadnought — Gallente':'Hubris', 'Lancer Dreadnought — Minmatar':'Valravn',
 'Supercarrier — Amarr':'Aeon', 'Supercarrier — Caldari':'Wyvern', 'Supercarrier — Gallente':'Nyx', 'Supercarrier — Minmatar':'Hel',
 'Titan — Amarr':'Avatar', 'Titan — Caldari':'Leviathan', 'Titan — Gallente':'Erebus', 'Titan — Minmatar':'Ragnarok',
}

def normalize_ship_name(value, default='Rhea'):
    name=LEGACY_SHIP_NAMES.get(str(value or '').strip(), str(value or '').strip())
    return name if name in SHIPS else default

def version_tuple(value):
    parts=[]
    for piece in str(value).strip().lstrip('vV').split('.'):
        try: parts.append(int(piece))
        except ValueError:
            digits=''.join(ch for ch in piece if ch.isdigit())
            parts.append(int(digits) if digits else 0)
    return tuple((parts+[0,0,0])[:3])

def _safe_update_relpath(value):
    rel=Path(str(value).replace('\\','/'))
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise RuntimeError(f'Unsafe update file path: {value!r}')
    return rel

def _sha256_file(path, chunk_size=1024*1024):
    import hashlib
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while True:
            chunk=f.read(chunk_size)
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()

def inspect_update_package(package_path):
    """Validate a .ejpupdate package and return its manifest."""
    pp=Path(package_path)
    if not pp.exists(): raise RuntimeError('Update file was not found.')
    try:
        z=zipfile.ZipFile(pp)
    except zipfile.BadZipFile as e:
        raise RuntimeError(f'This is not a valid {APP_NAME} update file.') from e
    with z:
        names={n.replace('\\','/') for n in z.namelist() if not n.endswith('/')}
        if 'manifest.json' not in names:
            raise RuntimeError('Update manifest.json is missing.')
        try: manifest=json.loads(z.read('manifest.json').decode('utf-8'))
        except Exception as e: raise RuntimeError('Update manifest is unreadable.') from e
        if manifest.get('format')!=UPDATE_FORMAT:
            raise RuntimeError(f"Unsupported update format {manifest.get('format')!r}.")
        if manifest.get('app_id')!=APP_ID:
            raise RuntimeError('This update file is for a different application.')
        ver=str(manifest.get('version') or '').strip()
        if not ver: raise RuntimeError('Update version is missing.')
        mode=manifest.get('mode')
        if mode not in ('source','frozen-onedir'):
            raise RuntimeError(f'Unsupported update mode: {mode!r}')
        files=manifest.get('files')
        if not isinstance(files,list) or not files:
            raise RuntimeError('Update contains no payload files.')
        seen=set()
        for entry in files:
            if not isinstance(entry,dict): raise RuntimeError('Invalid update file entry.')
            rel=_safe_update_relpath(entry.get('path',''))
            key=rel.as_posix()
            if key in seen: raise RuntimeError(f'Duplicate update file: {key}')
            seen.add(key)
            arc='payload/'+key
            if arc not in names: raise RuntimeError(f'Update payload is missing {key}.')
            sha=str(entry.get('sha256') or '').lower()
            if len(sha)!=64 or any(ch not in '0123456789abcdef' for ch in sha):
                raise RuntimeError(f'Invalid SHA-256 for {key}.')
            try: size=int(entry.get('size'))
            except Exception: raise RuntimeError(f'Invalid size for {key}.')
            info=z.getinfo(arc)
            if info.file_size!=size: raise RuntimeError(f'Size check failed for {key}.')
        return manifest

def extract_verified_update(package_path, destination):
    manifest=inspect_update_package(package_path)
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(package_path) as z:
        for entry in manifest['files']:
            rel=_safe_update_relpath(entry['path'])
            target=destination/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open('payload/'+rel.as_posix()) as src, open(target,'wb') as dst:
                shutil.copyfileobj(src,dst)
            if target.stat().st_size!=int(entry['size']):
                raise RuntimeError(f'Size verification failed for {rel}.')
            if _sha256_file(target)!=entry['sha256'].lower():
                raise RuntimeError(f'SHA-256 verification failed for {rel}.')
    return manifest

def _ps_quote(value):
    return "'"+str(value).replace("'", "''")+"'"

def _write_frozen_update_helper(stage_root, install_dir, backup_app, current_pid):
    """Create a temporary PowerShell helper that swaps the installed onedir runtime after exit."""
    helper=Path(tempfile.gettempdir())/f'eve-jump-planner-update-{int(time.time())}.ps1'
    log_path=BASE/'update-install.log'
    exe_name=APP_EXECUTABLE_NAME
    script=f"""$ErrorActionPreference = 'Stop'
$Source = {_ps_quote(stage_root)}
$Destination = {_ps_quote(install_dir)}
$Backup = {_ps_quote(backup_app)}
$ExeName = {_ps_quote(exe_name)}
$WaitPid = {int(current_pid)}
$Log = {_ps_quote(log_path)}
function Write-UpdateLog([string]$Text) {{
    try {{ Add-Content -Path $Log -Value ((Get-Date -Format s) + '  ' + $Text) -Encoding UTF8 }} catch {{}}
}}
Write-UpdateLog 'Update helper started.'
for ($i = 0; $i -lt 120; $i++) {{
    if (-not (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue)) {{ break }}
    Start-Sleep -Milliseconds 500
}}
if (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) {{
    Write-UpdateLog 'Timed out waiting for the application to exit.'
    exit 20
}}
try {{
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $null = & robocopy $Source $Destination /MIR /R:5 /W:1 /NFL /NDL /NJH /NJS /NP
    $Code = $LASTEXITCODE
    if ($Code -gt 7) {{ throw "robocopy failed with exit code $Code" }}
    $TargetExe = Join-Path $Destination $ExeName
    if (-not (Test-Path $TargetExe)) {{ throw "Updated executable is missing: $TargetExe" }}
    Write-UpdateLog 'Runtime files installed successfully.'
    Start-Process -FilePath $TargetExe -WorkingDirectory $Destination
    Remove-Item -Recurse -Force $Source -ErrorAction SilentlyContinue
    Write-UpdateLog 'Updated application started.'
    Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
    exit 0
}} catch {{
    Write-UpdateLog ('Update failed: ' + $_.Exception.Message)
    try {{
        if (Test-Path $Backup) {{
            New-Item -ItemType Directory -Force -Path $Destination | Out-Null
            $null = & robocopy $Backup $Destination /MIR /R:5 /W:1 /NFL /NDL /NJH /NJS /NP
            $RestoreCode = $LASTEXITCODE
            Write-UpdateLog ('Restore robocopy exit code: ' + $RestoreCode)
            $OldExe = Join-Path $Destination $ExeName
            if (Test-Path $OldExe) {{ Start-Process -FilePath $OldExe -WorkingDirectory $Destination }}
        }}
    }} catch {{ Write-UpdateLog ('Rollback failed: ' + $_.Exception.Message) }}
    exit 21
}}
"""
    helper.write_text(script,encoding='utf-8-sig')
    return helper

def install_update_package(package_path):
    """Prepare/install a verified update while preserving all user data."""
    manifest=inspect_update_package(package_path)
    new_version=str(manifest['version'])
    if version_tuple(new_version)<=version_tuple(VERSION):
        raise RuntimeError(f'Update v{new_version} is not newer than running v{VERSION}.')
    frozen=bool(getattr(sys,'frozen',False))
    wanted_mode='frozen-onedir' if frozen else 'source'
    if manifest.get('mode')!=wanted_mode:
        raise RuntimeError(f"This app needs a {wanted_mode} update, but the selected file is {manifest.get('mode')}.")
    BACKUPS.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    backup=BACKUPS/f'app-v{VERSION}-{stamp}'
    backup.mkdir(parents=True,exist_ok=True)
    stage_root=BASE/'updates'/f'v{new_version}-{stamp}'
    if stage_root.exists(): shutil.rmtree(stage_root,ignore_errors=True)
    extract_verified_update(package_path,stage_root)
    if frozen:
        current=Path(sys.executable).resolve()
        install_dir=current.parent
        staged=stage_root/APP_EXECUTABLE_NAME
        if not staged.exists():
            raise RuntimeError(f'Packaged update is missing {APP_EXECUTABLE_NAME}.')
        # The installer keeps the frozen runtime in its own app subdirectory,
        # so the updater can mirror only application runtime files without
        # touching the Inno Setup uninstaller or per-user data.
        backup_app=backup/'app'
        shutil.copytree(install_dir,backup_app,dirs_exist_ok=True)
        helper=_write_frozen_update_helper(stage_root,install_dir,backup_app,os.getpid())
        return new_version,backup,helper
    for name in ('app.py','VERSION','README.md','run.bat'):
        src=APP_DIR/name
        if src.exists(): shutil.copy2(src,backup/name)
    for src in stage_root.rglob('*'):
        if not src.is_file(): continue
        rel=src.relative_to(stage_root)
        dest=APP_DIR/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dest)
    shutil.rmtree(stage_root,ignore_errors=True)
    return new_version,backup,None

def _validate_update_feed_url(value):
    url=str(value or '').strip()
    if not url:
        raise RuntimeError('Enter an update feed URL first.')
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme.lower()!='https':
        raise RuntimeError('Update feeds must use HTTPS.')
    if not parsed.netloc:
        raise RuntimeError('Update feed URL is invalid.')
    return url

def fetch_update_feed(feed_url):
    """Download and validate the small JSON document describing the latest release."""
    feed_url=_validate_update_feed_url(feed_url)
    req=urllib.request.Request(feed_url,headers={'User-Agent':f'{APP_NAME}/{VERSION}','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as r:
        raw=r.read(1024*1024+1)
    if len(raw)>1024*1024:
        raise RuntimeError('Update feed is unexpectedly large.')
    try: data=json.loads(raw.decode('utf-8'))
    except Exception as e: raise RuntimeError('Update feed is not valid JSON.') from e
    if not isinstance(data,dict) or data.get('app_id')!=APP_ID:
        raise RuntimeError('Update feed is for a different application.')
    ver=str(data.get('version') or '').strip()
    if not ver: raise RuntimeError('Update feed does not contain a version.')
    update_url=str(data.get('update_url') or '').strip()
    if not update_url: raise RuntimeError('Update feed does not contain update_url.')
    update_url=urllib.parse.urljoin(feed_url,update_url)
    parsed=urllib.parse.urlparse(update_url)
    if parsed.scheme.lower()!='https': raise RuntimeError('Update package URL must use HTTPS.')
    sha=str(data.get('update_sha256') or '').strip().lower()
    if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
        raise RuntimeError('Update feed has an invalid update SHA-256.')
    result=dict(data); result['version']=ver; result['update_url']=update_url; result['update_sha256']=sha
    try: result['update_size']=int(data.get('update_size') or 0)
    except Exception: result['update_size']=0
    return result

def download_feed_update(feed,progress=lambda message,done,total:None):
    """Download the .ejpupdate named by a validated feed and verify the outer SHA-256."""
    DOWNLOADS.mkdir(parents=True,exist_ok=True)
    url=feed['update_url']; parsed=urllib.parse.urlparse(url)
    filename=Path(urllib.parse.unquote(parsed.path)).name or f'New_Eden_Command_Update_v{feed["version"]}.ejpupdate'
    if not filename.lower().endswith(UPDATE_EXTENSION):
        filename=f'New_Eden_Command_Update_v{feed["version"]}.ejpupdate'
    target=DOWNLOADS/filename; temp=target.with_suffix(target.suffix+'.part')
    req=urllib.request.Request(url,headers={'User-Agent':f'{APP_NAME}/{VERSION}','Accept':'application/octet-stream'})
    try:
        with urllib.request.urlopen(req,timeout=30) as r, open(temp,'wb') as f:
            header_total=int(r.headers.get('Content-Length') or 0)
            expected=int(feed.get('update_size') or 0)
            total=header_total or expected
            done=0
            while True:
                chunk=r.read(1024*256)
                if not chunk: break
                f.write(chunk); done+=len(chunk); progress('Downloading application update…',done,total)
        if expected and temp.stat().st_size!=expected:
            raise RuntimeError(f'Update download size check failed ({temp.stat().st_size:,} != {expected:,} bytes).')
        progress('Verifying downloaded update…',1,1)
        if _sha256_file(temp)!=feed['update_sha256']:
            raise RuntimeError('Downloaded update failed SHA-256 verification.')
        inspect_update_package(temp)
        os.replace(temp,target)
        return target
    except Exception:
        try: temp.unlink(missing_ok=True)
        except Exception: pass
        raise

def load_meta():
    try:return json.loads(META.read_text())
    except:return {}
def save_meta(m): META.write_text(json.dumps(m,indent=2))

def load_config():
    try:
        data=json.loads(CONFIG.read_text())
        if not isinstance(data,dict): raise ValueError
    except Exception:
        data={}
    data.setdefault('profiles',{})
    data.setdefault('routes',{})
    data.setdefault('app_state',{})
    data.setdefault('fuel_prices',{})
    data.setdefault('market_prices',{})
    data.setdefault('update_feed_url','https://github.com/jamesronaldthorn-cpu/New-Eden-Command/releases/latest/download/latest.json')
    if not str(data.get('update_feed_url','')).strip():
        data['update_feed_url']='https://github.com/jamesronaldthorn-cpu/New-Eden-Command/releases/latest/download/latest.json'
    data.setdefault('last_update_check_utc','')
    data.setdefault('live_jump_restrictions',{})
    data.setdefault('favorite_systems',[])
    data.setdefault('recent_routes',[])
    data.setdefault('operations',{})
    data.setdefault('active_operation','')
    data.setdefault('activity_cache',{})
    data.setdefault('companion_cache',{})
    data.setdefault('esi_name_cache',{})
    data.setdefault('notification_settings',{'industry_hours':2,'skillqueue_hours':24,'activity_score':75})
    sso=data.setdefault('esi_sso',{})
    if not isinstance(sso,dict):
        sso={}; data['esi_sso']=sso
    # v1.4 stored one character directly under esi_sso. Migrate it to the
    # multi-character store without discarding its DPAPI-protected token.
    chars=sso.get('characters')
    if not isinstance(chars,dict):
        chars={}
    legacy_cid=int(sso.get('character_id',0) or 0)
    if legacy_cid and str(legacy_cid) not in chars:
        chars[str(legacy_cid)]={
            'character_id':legacy_cid,
            'character_name':str(sso.get('character_name','')).strip() or f'Character {legacy_cid}',
            'skills':sso.get('skills',{}) if isinstance(sso.get('skills',{}),dict) else {},
            'last_sync_utc':str(sso.get('last_sync_utc','')),
            'refresh_token_dpapi':str(sso.get('refresh_token_dpapi','')),
            'scopes':list(sso.get('scopes',[])) if isinstance(sso.get('scopes',[]),list) else [],
        }
    sso['characters']=chars
    sso.setdefault('active_character_id',legacy_cid)
    sso.setdefault('auto_apply',True)
    # Developer application settings are build-time configuration in v1.5+.
    # Remove the old per-user copy after migrating the legacy character token.
    for legacy_key in ('client_id','redirect_uri','character_id','character_name','skills','last_sync_utc','refresh_token_dpapi'):
        sso.pop(legacy_key,None)
    return data

def save_config(data):
    BASE.mkdir(parents=True,exist_ok=True)
    CONFIG.write_text(json.dumps(data,indent=2,sort_keys=True))

def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

def _dpapi_blob_type():
    import ctypes
    from ctypes import wintypes
    class DATA_BLOB(ctypes.Structure):
        _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    return DATA_BLOB

def protect_refresh_token(value):
    """Protect an OAuth refresh token with Windows DPAPI for this Windows user."""
    if not value: return ''
    if os.name!='nt': return ''
    import ctypes
    DATA_BLOB=_dpapi_blob_type()
    raw=value.encode('utf-8')
    buf=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
    in_blob=DATA_BLOB(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)))
    out_blob=DATA_BLOB()
    crypt32=ctypes.windll.crypt32; kernel32=ctypes.windll.kernel32
    if not crypt32.CryptProtectData(ctypes.byref(in_blob),None,None,None,None,0,ctypes.byref(out_blob)):
        raise ctypes.WinError()
    try:
        protected=ctypes.string_at(out_blob.pbData,out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return base64.b64encode(protected).decode('ascii')

def unprotect_refresh_token(value):
    if not value or os.name!='nt': return ''
    import ctypes
    DATA_BLOB=_dpapi_blob_type()
    raw=base64.b64decode(value.encode('ascii'))
    buf=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
    in_blob=DATA_BLOB(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)))
    out_blob=DATA_BLOB()
    crypt32=ctypes.windll.crypt32; kernel32=ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob),None,None,None,None,0,ctypes.byref(out_blob)):
        raise ctypes.WinError()
    try:
        clear=ctypes.string_at(out_blob.pbData,out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return clear.decode('utf-8')

def fetch_sso_metadata():
    req=urllib.request.Request(SSO_WELL_KNOWN,headers={'User-Agent':f'{APP_NAME}/{VERSION}','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as r:
        data=json.load(r)
    if not data.get('authorization_endpoint') or not data.get('token_endpoint'):
        raise RuntimeError('EVE SSO metadata did not include the required OAuth endpoints.')
    return data

def _post_form(url,fields):
    body=urllib.parse.urlencode(fields).encode('utf-8')
    req=urllib.request.Request(url,data=body,headers={
        'User-Agent':f'{APP_NAME}/{VERSION}',
        'Accept':'application/json',
        'Content-Type':'application/x-www-form-urlencoded',
    })
    try:
        with urllib.request.urlopen(req,timeout=30) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        try: detail=e.read().decode('utf-8','replace')
        except Exception: detail=str(e)
        raise RuntimeError(f'EVE SSO returned HTTP {e.code}: {detail[:500]}') from e

def exchange_sso_code(client_id,redirect_uri,code,verifier,token_endpoint):
    return _post_form(token_endpoint,{
        'grant_type':'authorization_code','code':code,'client_id':client_id,
        'code_verifier':verifier,'redirect_uri':redirect_uri,
    })

def refresh_sso_access(client_id,refresh_token,token_endpoint):
    return _post_form(token_endpoint,{
        'grant_type':'refresh_token','refresh_token':refresh_token,'client_id':client_id,
    })

def verify_sso_access(access_token):
    req=urllib.request.Request(SSO_VERIFY,headers={
        'Authorization':f'Bearer {access_token}','User-Agent':f'{APP_NAME}/{VERSION}','Accept':'application/json'
    })
    with urllib.request.urlopen(req,timeout=20) as r: return json.load(r)

def fetch_character_skills(character_id,access_token):
    url=f'{ESI_BASE}/v4/characters/{int(character_id)}/skills/'
    req=urllib.request.Request(url,headers={
        'Authorization':f'Bearer {access_token}',
        'User-Agent':f'{APP_NAME}/{VERSION} CharacterSkillsClient',
        'Accept':'application/json','X-Compatibility-Date':esi_compatibility_date(),
    })
    try:
        with urllib.request.urlopen(req,timeout=30) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        try: detail=e.read().decode('utf-8','replace')
        except Exception: detail=str(e)
        raise RuntimeError(f'CCP ESI skills request returned HTTP {e.code}: {detail[:500]}') from e

def post_autopilot_waypoint(destination_id,access_token,clear_other_waypoints=True,add_to_beginning=False):
    """Set an EVE client autopilot waypoint for the authenticated character.

    CCP's UI endpoint accepts a solar-system, station, or structure ID.  We use
    solar-system IDs from the SDE.  This changes the in-game autopilot waypoint
    list; it does not initiate a capital jump or control the ship.
    """
    params=urllib.parse.urlencode({
        'add_to_beginning':'true' if add_to_beginning else 'false',
        'clear_other_waypoints':'true' if clear_other_waypoints else 'false',
        'destination_id':int(destination_id),
        'datasource':'tranquility',
    })
    url=f'{ESI_BASE}/latest/ui/autopilot/waypoint/?{params}'
    req=urllib.request.Request(url,data=b'',method='POST',headers={
        'Authorization':f'Bearer {access_token}',
        'User-Agent':f'{APP_NAME}/{VERSION} InGameWaypointClient',
        'Accept':'application/json',
        'X-Compatibility-Date':esi_compatibility_date(),
    })
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            if getattr(r,'status',204) not in (200,204):
                raise RuntimeError(f'CCP ESI returned HTTP {getattr(r,"status","?")} while setting the waypoint.')
    except urllib.error.HTTPError as e:
        try: detail=e.read().decode('utf-8','replace')
        except Exception: detail=str(e)
        raise RuntimeError(f'CCP ESI waypoint request returned HTTP {e.code}: {detail[:500]}') from e

def _esi_headers(access_token=None, client_name='CompanionClient'):
    headers={
        'User-Agent':f'{APP_NAME}/{VERSION} {client_name}',
        'Accept':'application/json',
        'X-Compatibility-Date':esi_compatibility_date(),
    }
    if access_token: headers['Authorization']=f'Bearer {access_token}'
    return headers

def esi_get_json(path,access_token=None,params=None,timeout=30,client_name='CompanionClient'):
    """Small ESI GET wrapper using the app compatibility date."""
    params=dict(params or {})
    params.setdefault('datasource','tranquility')
    q=urllib.parse.urlencode(params,doseq=True)
    url=f'{ESI_BASE}{path}' + (('?' + q) if q else '')
    req=urllib.request.Request(url,headers=_esi_headers(access_token,client_name))
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            body=r.read()
            return json.loads(body.decode('utf-8')) if body else None, dict(r.headers.items())
    except urllib.error.HTTPError as e:
        try: detail=e.read().decode('utf-8','replace')
        except Exception: detail=str(e)
        raise RuntimeError(f'CCP ESI returned HTTP {e.code} for {path}: {detail[:500]}') from e

def esi_post_json(path,payload,access_token=None,params=None,timeout=30,client_name='CompanionClient'):
    params=dict(params or {}); params.setdefault('datasource','tranquility')
    q=urllib.parse.urlencode(params,doseq=True)
    url=f'{ESI_BASE}{path}' + (('?' + q) if q else '')
    body=json.dumps(payload).encode('utf-8')
    headers=_esi_headers(access_token,client_name); headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=body,method='POST',headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read(); return json.loads(raw.decode('utf-8')) if raw else None, dict(r.headers.items())
    except urllib.error.HTTPError as e:
        try:detail=e.read().decode('utf-8','replace')
        except Exception:detail=str(e)
        raise RuntimeError(f'CCP ESI returned HTTP {e.code} for {path}: {detail[:500]}') from e

def resolve_universe_names(ids):
    clean=[]
    for value in ids or []:
        try:i=int(value)
        except Exception:continue
        if i>0 and i not in clean:clean.append(i)
    out={}
    for pos in range(0,len(clean),1000):
        chunk=clean[pos:pos+1000]
        if not chunk:continue
        try:data,_=esi_post_json('/latest/universe/names',chunk,None,client_name='NameResolverClient')
        except RuntimeError as e:
            # ESI returns 404 when none of the IDs in a chunk are resolvable.
            if 'HTTP 404' in str(e):continue
            raise
        for row in data or []:
            try:rid=int(row.get('id'))
            except Exception:continue
            out[rid]={'name':str(row.get('name') or '').strip(),'category':str(row.get('category') or '').strip()}
    return out

def resolve_structure_info(structure_id,access_token):
    try:data,_=esi_get_json(f'/latest/universe/structures/{int(structure_id)}',access_token,client_name='StructureNameResolver')
    except Exception:return None
    if not isinstance(data,dict):return None
    return {'name':str(data.get('name') or '').strip(),'category':'structure','system_id':int(data.get('solar_system_id') or 0),'type_id':int(data.get('type_id') or 0)}

def resolve_station_info(station_id):
    """Resolve an NPC station that is missing from the local SDE station index.

    This is a public ESI fallback used by the asset grouper.  The local SDE remains
    the fast path; this call is only made for root asset locations that still have
    no solar-system mapping.
    """
    try:data,_=esi_get_json(f'/latest/universe/stations/{int(station_id)}',None,client_name='StationLocationResolver')
    except Exception:return None
    if not isinstance(data,dict):return None
    try:sid=int(data.get('system_id') or 0)
    except Exception:sid=0
    if not sid:return None
    return {
        'name':str(data.get('name') or '').strip() or f'NPC Station {int(station_id)}',
        'category':'station',
        'system_id':sid,
        'type_id':int(data.get('type_id') or 0),
    }

def asset_flag_is_fitted(flag):
    """Return True for inventory flags representing modules fitted to a ship.

    Cargo, drone/fighter bays, fleet hangars and ship maintenance bays are not
    considered fitted and remain part of the asset inventory/valuation.
    """
    value=str(flag or '')
    for prefix in ('HiSlot','MedSlot','LoSlot','RigSlot','SubSystemSlot','ServiceSlot'):
        if value.startswith(prefix) and value[len(prefix):].isdigit():
            return True
    return False

def fetch_contract_items(character_id,contract_id,access_token):
    data,_=esi_get_json(f'/latest/characters/{int(character_id)}/contracts/{int(contract_id)}/items',access_token,client_name='ContractItemsClient')
    return data if isinstance(data,list) else []

def esi_get_paginated(path,access_token,params=None,max_pages=None,client_name='CompanionClient'):
    """Read every advertised ESI page unless an explicit safety cap is supplied.

    Asset inventories can legitimately exceed sixty 1,000-row pages, so silently
    truncating at the old desktop cap could hide entire systems from Asset Finder.
    """
    out=[]; page=1; pages=1
    while page<=pages and (max_pages is None or page<=max_pages):
        p=dict(params or {}); p['page']=page
        data,headers=esi_get_json(path,access_token,p,45,client_name)
        if isinstance(data,list): out.extend(data)
        elif data is not None: return data
        try: pages=max(1,int(headers.get('X-Pages') or headers.get('x-pages') or 1))
        except Exception: pages=1
        page+=1
    return out

def post_open_market_details(type_id,access_token):
    params=urllib.parse.urlencode({'type_id':int(type_id),'datasource':'tranquility'})
    req=urllib.request.Request(f'{ESI_BASE}/latest/ui/openwindow/marketdetails/?{params}',data=b'',method='POST',headers=_esi_headers(access_token,'OpenMarketClient'))
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            if getattr(r,'status',204) not in (200,204): raise RuntimeError('EVE client did not accept the market-window request.')
    except urllib.error.HTTPError as e:
        try: detail=e.read().decode('utf-8','replace')
        except Exception: detail=str(e)
        raise RuntimeError(f'CCP ESI market-window request returned HTTP {e.code}: {detail[:500]}') from e

def post_open_contract(contract_id,access_token):
    params=urllib.parse.urlencode({'contract_id':int(contract_id),'datasource':'tranquility'})
    req=urllib.request.Request(f'{ESI_BASE}/latest/ui/openwindow/contract/?{params}',data=b'',method='POST',headers=_esi_headers(access_token,'OpenContractClient'))
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            if getattr(r,'status',204) not in (200,204): raise RuntimeError('EVE client did not accept the contract-window request.')
    except urllib.error.HTTPError as e:
        try: detail=e.read().decode('utf-8','replace')
        except Exception: detail=str(e)
        raise RuntimeError(f'CCP ESI contract-window request returned HTTP {e.code}: {detail[:500]}') from e

def fetch_character_companion_snapshot(character_id,access_token,scopes):
    """Fetch the power-user character datasets for every scope currently granted.

    Each sub-request is isolated so one unavailable route does not blank the rest of
    the dashboard.  The snapshot is safe to cache because refresh tokens are never
    included in it.
    """
    cid=int(character_id); scopes=set(scopes or [])
    snap={'character_id':cid,'fetched_at':int(time.time()),'errors':{}}
    def grab(key,path,scope=None,paginated=False):
        if scope and scope not in scopes:
            snap[key]=None; return
        try:
            if paginated: snap[key]=esi_get_paginated(path,access_token,client_name='CommandCenterClient')
            else: snap[key]=esi_get_json(path,access_token,client_name='CommandCenterClient')[0]
        except Exception as e:
            snap[key]=None; snap['errors'][key]=str(e)
    grab('public',f'/latest/characters/{cid}/')
    grab('location',f'/latest/characters/{cid}/location/',ESI_LOCATION_SCOPE)
    grab('ship',f'/latest/characters/{cid}/ship/',ESI_SHIP_SCOPE)
    grab('online',f'/latest/characters/{cid}/online/',ESI_ONLINE_SCOPE)
    grab('wallet',f'/latest/characters/{cid}/wallet/',ESI_WALLET_SCOPE)
    grab('skills_full',f'/v4/characters/{cid}/skills/',ESI_SKILLS_SCOPE)
    grab('skillqueue',f'/latest/characters/{cid}/skillqueue/',ESI_SKILLQUEUE_SCOPE)
    grab('clones',f'/latest/characters/{cid}/clones/',ESI_CLONES_SCOPE)
    grab('industry_jobs',f'/latest/characters/{cid}/industry/jobs/',ESI_INDUSTRY_SCOPE)
    grab('contracts',f'/latest/characters/{cid}/contracts/',ESI_CONTRACTS_SCOPE,paginated=True)
    grab('assets',f'/latest/characters/{cid}/assets/',ESI_ASSETS_SCOPE,paginated=True)
    return snap

def fetch_public_activity():
    """Public last-hour system jump and kill activity from CCP ESI."""
    kills,_=esi_get_json('/latest/universe/system_kills/',None,client_name='ActivityIntelClient')
    jumps,_=esi_get_json('/latest/universe/system_jumps/',None,client_name='ActivityIntelClient')
    by={}
    for row in kills or []:
        try:sid=int(row.get('system_id'))
        except Exception:continue
        rec=by.setdefault(sid,{})
        rec.update({'ship_kills':int(row.get('ship_kills',0) or 0),'pod_kills':int(row.get('pod_kills',0) or 0),'npc_kills':int(row.get('npc_kills',0) or 0)})
    for row in jumps or []:
        try:sid=int(row.get('system_id'))
        except Exception:continue
        by.setdefault(sid,{})['ship_jumps']=int(row.get('ship_jumps',0) or 0)
    return {'systems':{str(k):v for k,v in by.items()},'fetched_at':int(time.time()),'source':'CCP ESI system_kills + system_jumps'}

def activity_score(rec):
    """Heuristic activity score, intentionally labelled as activity rather than safety."""
    rec=rec or {}
    ship=int(rec.get('ship_kills',0) or 0); pod=int(rec.get('pod_kills',0) or 0); jumps=int(rec.get('ship_jumps',0) or 0)
    return min(999, ship*8 + pod*14 + min(60,jumps//20))

def skill_levels_from_esi(payload):
    by_id={int(x.get('skill_id',0)):int(x.get('trained_skill_level',x.get('active_skill_level',0)) or 0) for x in payload.get('skills',[]) if isinstance(x,dict)}
    return {name:max(0,min(5,by_id.get(type_id,0))) for name,type_id in CHARACTER_SKILLS.items()}

def load_asset_market_price_cache():
    try:
        data=json.loads(ASSET_PRICE_CACHE.read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except Exception:
        return {}

def save_asset_market_price_cache(data):
    try:
        DATA.mkdir(parents=True,exist_ok=True)
        ASSET_PRICE_CACHE.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    except Exception:
        pass

def fetch_asset_market_prices():
    """Fetch CCP's public universe-wide market reference prices.

    The asset dashboard uses average_price when CCP supplies one and falls back
    to adjusted_price.  This is deliberately labelled an *estimate*: it is a
    fast, universe-wide reference suitable for valuing thousands of assets
    without issuing one regional order-book request per item type.
    """
    data,_=esi_get_json('/latest/markets/prices/',None,timeout=45,client_name='AssetValuationClient')
    prices={}
    average_count=0
    adjusted_count=0
    for row in data or []:
        if not isinstance(row,dict):continue
        try:tid=int(row.get('type_id') or 0)
        except Exception:continue
        if tid<=0:continue
        value=None
        try:
            avg=float(row.get('average_price')) if row.get('average_price') is not None else None
            if avg is not None and avg>0:
                value=avg; average_count+=1
        except Exception:
            value=None
        if value is None:
            try:
                adj=float(row.get('adjusted_price')) if row.get('adjusted_price') is not None else None
                if adj is not None and adj>0:
                    value=adj; adjusted_count+=1
            except Exception:
                value=None
        if value is not None:prices[str(tid)]=value
    if not prices:
        raise RuntimeError('CCP ESI returned no usable market reference prices.')
    return {
        'fetched_at':int(time.time()),
        'prices':prices,
        'source':'CCP ESI average_price (adjusted_price fallback)',
        'average_count':average_count,
        'adjusted_count':adjusted_count,
    }

def validate_loopback_redirect(uri):
    parsed=urllib.parse.urlparse(str(uri).strip())
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or not parsed.port:
        raise RuntimeError('Desktop EVE login needs a loopback callback such as http://127.0.0.1:8765/callback.')
    return parsed

def esi_compatibility_date():
    # ESI's compatibility day changes at 11:00 UTC. Using now-11h avoids ever
    # sending tomorrow's compatibility date during the pre-downtime window.
    return (datetime.now(timezone.utc)-timedelta(hours=11)).date().isoformat()

def fetch_jita_isotope_prices(progress=lambda message,done,total:None):
    """Fetch Jita 4-4 isotope order-book prices from CCP's public ESI.

    Fuel-cost calculations use the lowest current sell order at station
    60003760 (Jita IV - Moon 4 - Caldari Navy Assembly Plant). Best buy is
    also captured for reference. No EVE login/SSO is required for this route.
    """
    best_sell={}; best_buy={}
    items=list(ISOTOPE_TYPE_IDS.items())
    for idx,(isotope,type_id) in enumerate(items,1):
        progress(f'Fetching {isotope} from Jita 4-4…',idx-1,len(items))
        page=1; pages=1
        sells=[]; buys=[]
        while page<=pages:
            query=urllib.parse.urlencode({'order_type':'all','type_id':type_id,'page':page})
            url=f'{ESI_BASE}/markets/{THE_FORGE_REGION_ID}/orders/?{query}'
            req=urllib.request.Request(url,headers={
                'User-Agent':f'{APP_NAME}/{VERSION} JitaFuelPriceClient',
                'Accept':'application/json',
                'X-Compatibility-Date':esi_compatibility_date(),
            })
            with urllib.request.urlopen(req,timeout=30) as r:
                if page==1:
                    try: pages=max(1,int(r.headers.get('X-Pages') or 1))
                    except (TypeError,ValueError): pages=1
                orders=json.load(r)
            for order in orders:
                try:
                    if int(order.get('location_id',0))!=JITA_44_STATION_ID: continue
                    price=float(order.get('price'))
                except (TypeError,ValueError):
                    continue
                if order.get('is_buy_order'): buys.append(price)
                else: sells.append(price)
            page+=1
        if not sells:
            raise RuntimeError(f'CCP ESI returned no Jita 4-4 sell orders for {isotope}.')
        best_sell[isotope]=min(sells)
        best_buy[isotope]=max(buys) if buys else None
        progress(f'Loaded {isotope}',idx,len(items))
    return {'sell':best_sell,'buy':best_buy,'fetched_at':int(time.time()),'source':'CCP ESI — Jita 4-4'}

def latest_build():
    with urllib.request.urlopen(LATEST,timeout=20) as r:
        for raw in r:
            x=json.loads(raw)
            if x.get('_key')=='sde': return str(x.get('_value') or x.get('buildNumber') or x.get('value'))
    raise RuntimeError('Could not read CCP SDE build number')

def locate_member(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix): return n
    raise RuntimeError(f'{suffix} not found in SDE')

def database_schema_ready():
    if not DB.exists(): return False
    try:
        c=sqlite3.connect(DB)
        has_regions=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='regions'").fetchone())
        has_types=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='types'").fetchone())
        has_stations=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stations'").fetchone())
        has_stargates=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stargates'").fetchone())
        has_skill_requirements=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_requirements'").fetchone())
        has_skill_meta=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_meta'").fetchone())
        cols={str(r[1]) for r in c.execute('PRAGMA table_info(systems)').fetchall()}
        type_count=int(c.execute('SELECT COUNT(*) FROM types').fetchone()[0]) if has_types else 0
        # Known types make this an integrity check, not merely a table-exists check.
        # Older builds could leave an empty `types` table and still report the DB current,
        # which is what caused Item / Ship / Skill columns to display Unknown.
        known_names={int(r[0]):str(r[1]) for r in c.execute('SELECT id,name FROM types WHERE id IN (34,21611,29029)').fetchall()} if has_types else {}
        c.close()
        # The static type index is useful, but it must never brick the whole
        # navigation database.  Current ESI can repair individual missing type
        # names on demand, so schema readiness is based on the map/routing data
        # and the existence of the type table rather than three hard-coded
        # probe IDs.  This prevents a transient/partial SDE type export from
        # forcing an endless rebuild loop at 98%.
        names_ok=type_count>0
        return has_regions and has_types and has_stations and has_stargates and has_skill_requirements and has_skill_meta and names_ok and 'station_count' in cols and int(load_meta().get('schema_version',0) or 0)>=SDE_SCHEMA_VERSION
    except Exception:
        return False

def update_sde(progress=lambda message,percent=None:None):
    progress('Checking CCP SDE version…', 2)
    build=latest_build(); meta=load_meta()
    schema_ok=database_schema_ready()
    if str(meta.get('sde_build'))==build and DB.exists() and schema_ok:
        progress(f'CCP SDE build {build} is already current.', 100)
        return build,False

    progress(f'Downloading CCP SDE build {build}…', 5)
    req=urllib.request.Request(SDE_URL.format(build=build),headers={'User-Agent':f'{APP_NAME}/{VERSION}'})
    with urllib.request.urlopen(req,timeout=120) as r, tempfile.NamedTemporaryFile(delete=False,suffix='.zip') as f:
        try:
            total=int(r.headers.get('Content-Length') or 0)
        except (TypeError,ValueError):
            total=0
        downloaded=0
        while True:
            chunk=r.read(1024*1024)
            if not chunk: break
            f.write(chunk); downloaded+=len(chunk)
            if total:
                pct=5 + (downloaded/total)*60
                progress(f'Downloading CCP SDE build {build}… {downloaded/1024/1024:.1f} / {total/1024/1024:.1f} MB', pct)
            else:
                progress(f'Downloading CCP SDE build {build}… {downloaded/1024/1024:.1f} MB', None)
        tmp=f.name

    progress('Preparing EVE database…', 67)
    newdb=DB.with_suffix('.new')
    if newdb.exists(): newdb.unlink()
    con=sqlite3.connect(newdb); cur=con.cursor()
    cur.execute('CREATE TABLE systems(id INTEGER PRIMARY KEY,name TEXT COLLATE NOCASE,x REAL,y REAL,z REAL,security REAL,region_id INTEGER,constellation_id INTEGER,station_count INTEGER NOT NULL DEFAULT 0)')
    cur.execute('CREATE INDEX ix_system_name ON systems(name)')
    cur.execute('CREATE TABLE regions(id INTEGER PRIMARY KEY,name TEXT COLLATE NOCASE)')
    cur.execute('CREATE TABLE types(id INTEGER PRIMARY KEY,name TEXT COLLATE NOCASE,group_id INTEGER,market_group_id INTEGER,volume REAL,published INTEGER)')
    cur.execute('CREATE INDEX ix_type_name ON types(name)')
    cur.execute('CREATE TABLE stations(id INTEGER PRIMARY KEY,system_id INTEGER,type_id INTEGER,owner_id INTEGER,owner_name TEXT,operation_id INTEGER,operation_name TEXT,name TEXT)')
    cur.execute('CREATE INDEX ix_station_system ON stations(system_id)')
    cur.execute('CREATE TABLE stargates(a INTEGER NOT NULL,b INTEGER NOT NULL,PRIMARY KEY(a,b))')
    cur.execute('CREATE INDEX ix_stargates_a ON stargates(a)')
    cur.execute('CREATE INDEX ix_stargates_b ON stargates(b)')
    cur.execute('CREATE TABLE skill_requirements(skill_type_id INTEGER NOT NULL,required_skill_id INTEGER NOT NULL,required_level INTEGER NOT NULL,PRIMARY KEY(skill_type_id,required_skill_id))')
    cur.execute('CREATE INDEX ix_skill_req_skill ON skill_requirements(skill_type_id)')
    cur.execute('CREATE TABLE skill_meta(skill_type_id INTEGER PRIMARY KEY,rank REAL,primary_attr INTEGER,secondary_attr INTEGER)')
    count=0
    with zipfile.ZipFile(tmp) as z:
        # Region names are imported too so autocomplete can show System — Region.
        progress('Importing region names…', 69)
        rmember=locate_member(z,'mapRegions.jsonl')
        with z.open(rmember) as rfh:
            rrows=[]
            for raw in rfh:
                r=json.loads(raw); rid=int(r.get('_key',r.get('regionID',0)))
                name=r.get('name')
                if isinstance(name,dict): name=name.get('en') or name.get('en-us') or next(iter(name.values()),str(rid))
                if rid and name: rrows.append((rid,str(name)))
            cur.executemany('INSERT OR REPLACE INTO regions VALUES(?,?)',rrows)

        progress('Indexing item names for assets and logistics…', 70)
        type_import_error=''
        try:
            tmember=locate_member(z,'types.jsonl')
            with z.open(tmember) as tfh:
                trows=[]
                for raw in tfh:
                    t=json.loads(raw)
                    # CCP JSONL uses `_key` for integer-keyed datasets.  Keep a
                    # compatibility fallback for alternative/older exports.
                    tid=int(t.get('_key',t.get('typeID',t.get('type_id',0))) or 0)
                    name=t.get('name')
                    if isinstance(name,dict):
                        name=name.get('en') or name.get('en-us') or name.get('en_US') or next((v for v in name.values() if v),str(tid))
                    if not tid or not name: continue
                    volume=t.get('volume',t.get('packagedVolume'))
                    trows.append((tid,str(name),t.get('groupID',t.get('group_id')),t.get('marketGroupID',t.get('market_group_id')),volume,1 if t.get('published',True) else 0))
                    if len(trows)>=4000:
                        cur.executemany('INSERT OR REPLACE INTO types VALUES(?,?,?,?,?,?)',trows); trows=[]
                if trows: cur.executemany('INSERT OR REPLACE INTO types VALUES(?,?,?,?,?,?)',trows)
        except Exception as e:
            # Map/routing data is still valuable even if CCP's type-name table
            # has a transient issue.  v3.3.2 finishes the SDE update and lets the
            # public /universe/types/{type_id} route repair names on demand.
            type_import_error=str(e)

        # Import skill prerequisites and training metadata from CCP typeDogma.
        # Required-skill pairs are documented by CCP as 182/277, 183/278,
        # 184/279, 1285/1286, 1289/1287 and 1290/1288.
        progress('Indexing skill prerequisites…', 71)
        try:
            dmember=locate_member(z,'typeDogma.jsonl')
            req_attr_ids=(182,183,184,1285,1289,1290)
            req_level_ids=(277,278,279,1286,1287,1288)
            with z.open(dmember) as dfh:
                req_rows=[]; meta_rows=[]
                for raw in dfh:
                    d=json.loads(raw); tid=int(d.get('_key',0) or 0)
                    if not tid: continue
                    amap={int(a.get('attributeID',0) or 0):a.get('value') for a in (d.get('dogmaAttributes') or []) if isinstance(a,dict)}
                    if 275 in amap:
                        try:rank=float(amap.get(275) or 0)
                        except Exception:rank=0.0
                        try:primary=int(float(amap.get(180) or 0))
                        except Exception:primary=0
                        try:secondary=int(float(amap.get(181) or 0))
                        except Exception:secondary=0
                        meta_rows.append((tid,rank,primary,secondary))
                    for aid,lid in zip(req_attr_ids,req_level_ids):
                        try:req=int(float(amap.get(aid) or 0)); lvl=int(float(amap.get(lid) or 0))
                        except Exception:continue
                        if req>0 and lvl>0:req_rows.append((tid,req,lvl))
                    if len(req_rows)>=5000:
                        cur.executemany('INSERT OR REPLACE INTO skill_requirements VALUES(?,?,?)',req_rows); req_rows=[]
                    if len(meta_rows)>=5000:
                        cur.executemany('INSERT OR REPLACE INTO skill_meta VALUES(?,?,?,?)',meta_rows); meta_rows=[]
                if req_rows:cur.executemany('INSERT OR REPLACE INTO skill_requirements VALUES(?,?,?)',req_rows)
                if meta_rows:cur.executemany('INSERT OR REPLACE INTO skill_meta VALUES(?,?,?,?)',meta_rows)
        except Exception as e:
            raise RuntimeError(f'Could not import CCP skill prerequisites from typeDogma.jsonl: {e}') from e

        npc_names={}; operation_names={}
        try:
            cmember=locate_member(z,'npcCorporations.jsonl')
            with z.open(cmember) as cfh:
                for raw in cfh:
                    r=json.loads(raw); rid=int(r.get('_key',r.get('corporationID',0)) or 0); name=r.get('name')
                    if isinstance(name,dict): name=name.get('en') or name.get('en-us') or next(iter(name.values()),str(rid))
                    if rid and name: npc_names[rid]=str(name)
        except Exception: pass
        try:
            omember=locate_member(z,'stationOperations.jsonl')
            with z.open(omember) as ofh:
                for raw in ofh:
                    r=json.loads(raw); rid=int(r.get('_key',r.get('operationID',0)) or 0); name=r.get('name')
                    if isinstance(name,dict): name=name.get('en') or name.get('en-us') or next(iter(name.values()),str(rid))
                    if rid and name: operation_names[rid]=str(name)
        except Exception: pass

        member=locate_member(z,'mapSolarSystems.jsonl')
        member_size=max(1,z.getinfo(member).file_size)
        progress('Importing solar systems…', 72)
        with z.open(member) as fh:
            rows=[]; processed=0
            for raw in fh:
                processed+=len(raw)
                s=json.loads(raw)
                sid=int(s.get('_key',s.get('solarSystemID',0)))
                if 30000000 <= sid <= 30999999:
                    p=s.get('position') or {}
                    name=s.get('name')
                    if isinstance(name,dict): name=name.get('en') or name.get('en-us') or next(iter(name.values()),str(sid))
                    rows.append((sid,str(name),p.get('x',0),p.get('y',0),p.get('z',0),s.get('securityStatus',0),s.get('regionID'),s.get('constellationID'),0))
                    if len(rows)>=1000:
                        cur.executemany('INSERT INTO systems VALUES(?,?,?,?,?,?,?,?,?)',rows); count+=len(rows); rows=[]
                if count % 1000 == 0:
                    pct=72 + min(1.0,processed/member_size)*25
                    progress(f'Importing solar systems… {count:,} loaded', pct)
            if rows: cur.executemany('INSERT INTO systems VALUES(?,?,?,?,?,?,?,?,?)',rows); count+=len(rows)

        # Stargate graph powers the Hunting / Roam Intelligence scanner.
        progress('Indexing stargate connections…', 96)
        gate_pairs=set()
        try:
            gmember=locate_member(z,'mapStargates.jsonl')
            with z.open(gmember) as gfh:
                batch=[]
                for raw in gfh:
                    g=json.loads(raw)
                    try:
                        a=int(g.get('solarSystemID') or 0)
                        b=int((g.get('destination') or {}).get('solarSystemID') or 0)
                    except (TypeError,ValueError):
                        continue
                    if not a or not b or a==b: continue
                    lo,hi=(a,b) if a<b else (b,a)
                    if (lo,hi) in gate_pairs: continue
                    gate_pairs.add((lo,hi)); batch.append((lo,hi))
                    if len(batch)>=2500:
                        cur.executemany('INSERT OR IGNORE INTO stargates VALUES(?,?)',batch); batch=[]
                if batch: cur.executemany('INSERT OR IGNORE INTO stargates VALUES(?,?)',batch)
        except Exception:
            gate_pairs=set()

        # NPC station presence + station metadata power routing and the station panel.
        progress('Indexing NPC stations and services…', 97)
        station_total=0
        try:
            smember=locate_member(z,'npcStations.jsonl')
            station_counts={}; station_rows=[]
            with z.open(smember) as sfh:
                for raw in sfh:
                    st=json.loads(raw)
                    try:
                        station_id=int(st.get('_key',st.get('stationID',0)) or 0); sid=int(st.get('solarSystemID') or 0)
                    except (TypeError,ValueError): continue
                    if not station_id or not sid: continue
                    owner=int(st.get('ownerID') or 0); op=int(st.get('operationID') or 0); typ=int(st.get('typeID') or 0)
                    name=st.get('name') or ''
                    if isinstance(name,dict): name=name.get('en') or name.get('en-us') or next(iter(name.values()),'')
                    station_rows.append((station_id,sid,typ,owner,npc_names.get(owner,''),op,operation_names.get(op,''),str(name)))
                    station_counts[sid]=station_counts.get(sid,0)+1; station_total+=1
                    if len(station_rows)>=1500:
                        cur.executemany('INSERT OR REPLACE INTO stations VALUES(?,?,?,?,?,?,?,?)',station_rows); station_rows=[]
                if station_rows: cur.executemany('INSERT OR REPLACE INTO stations VALUES(?,?,?,?,?,?,?,?)',station_rows)
            cur.executemany('UPDATE systems SET station_count=? WHERE id=?',[(n,sid) for sid,n in station_counts.items()])
        except Exception:
            station_total=0

    progress('Validating EVE item, ship and skill names…', 98)
    con.commit()
    type_total=0; probes={}
    try:
        type_total=int(cur.execute('SELECT COUNT(*) FROM types').fetchone()[0])
        probes={int(r[0]):str(r[1]) for r in cur.execute('SELECT id,name FROM types WHERE id IN (34,21611,29029)').fetchall()}
        # Do not reject an otherwise valid map database solely because the SDE
        # type-name dataset is partial.  Missing names are repaired from CCP ESI
        # when the relevant character/assets/contracts/skills are displayed.
        # Seed the three diagnostic rows when possible so the local cache also
        # proves that the public resolver is working.
        missing=[tid for tid in (34,21611,29029) if not probes.get(tid)]
        if missing:
            progress(f'Type index has {type_total:,} rows; repairing {len(missing)} core names from CCP ESI…',98)
            for tid in missing:
                rec=_fetch_type_from_esi(tid)
                if rec:
                    cur.execute('INSERT OR REPLACE INTO types(id,name,group_id,market_group_id,volume,published) VALUES(?,?,?,?,?,?)',rec)
                    probes[int(rec[0])]=str(rec[1])
            con.commit()
            type_total=int(cur.execute('SELECT COUNT(*) FROM types').fetchone()[0])
        # Absolute last-resort seed names keep the DB schema usable offline.
        # These IDs/names are stable EVE inventory types and are only used when
        # both the SDE and ESI are unavailable; normal display names continue to
        # come from CCP data.
        seeds={34:'Tritanium',21611:'Jump Drive Calibration',29029:'Jump Freighters'}
        for tid,name in seeds.items():
            if not probes.get(tid):
                cur.execute('INSERT OR IGNORE INTO types(id,name,group_id,market_group_id,volume,published) VALUES(?,?,?,?,?,?)',(tid,name,None,None,None,1))
        con.commit(); type_total=int(cur.execute('SELECT COUNT(*) FROM types').fetchone()[0])
    finally:
        con.close()
    os.replace(newdb,DB); os.unlink(tmp)
    meta['sde_build']=build; meta['schema_version']=SDE_SCHEMA_VERSION; meta['system_count']=count; meta['npc_station_count']=locals().get('station_total',0); meta['stargate_connection_count']=len(locals().get('gate_pairs',set())); meta['type_name_count']=type_total; meta['type_name_health']='full' if type_total>=10000 else 'repair-on-demand'; meta['type_import_error']=locals().get('type_import_error',''); save_meta(meta)
    suffix='' if type_total>=10000 else ' • type names will self-repair from CCP ESI as needed'
    progress(f'Imported {count:,} systems, {int(locals().get("station_total",0)):,} NPC stations, {len(locals().get("gate_pairs",set())):,} stargate links and {type_total:,} type names{suffix}. EVE data is ready.', 100)
    return build,True


def system(name):
    if not DB.exists(): return None
    con=sqlite3.connect(DB)
    sql='SELECT s.id,s.name,s.x,s.y,s.z,s.security,s.region_id,COALESCE(r.name,"Unknown region"),COALESCE(s.station_count,0) FROM systems s LEFT JOIN regions r ON r.id=s.region_id WHERE s.name=?'
    try:
        r=con.execute(sql,(name.strip(),)).fetchone()
    except sqlite3.OperationalError:
        # Graceful read compatibility while an older local DB is waiting for the
        # automatic v2 station-aware SDE rebuild.
        old='SELECT s.id,s.name,s.x,s.y,s.z,s.security,s.region_id,COALESCE(r.name,"Unknown region") FROM systems s LEFT JOIN regions r ON r.id=s.region_id WHERE s.name=?'
        base=con.execute(old,(name.strip(),)).fetchone(); r=(tuple(base)+(0,)) if base else None
    con.close(); return r

def suggestions(prefix,limit=12):
    if not DB.exists() or not prefix.strip(): return []
    con=sqlite3.connect(DB)
    try:
        rs=con.execute('SELECT s.name,COALESCE(r.name,"Unknown region"),COALESCE(s.station_count,0) FROM systems s LEFT JOIN regions r ON r.id=s.region_id WHERE s.name LIKE ? ORDER BY s.name LIMIT ?', (prefix.strip()+'%',limit)).fetchall()
    except sqlite3.OperationalError:
        rs=[(r[0],'Update EVE data',0) for r in con.execute('SELECT name FROM systems WHERE name LIKE ? ORDER BY name LIMIT ?', (prefix.strip()+'%',limit)).fetchall()]
    con.close(); return rs

TYPE_NAME_RUNTIME_CACHE={}

def _local_type_name(type_id):
    try:tid=int(type_id)
    except Exception:return None
    cached=TYPE_NAME_RUNTIME_CACHE.get(tid)
    if cached:return cached
    if not DB.exists():return None
    try:
        con=sqlite3.connect(DB); row=con.execute('SELECT name FROM types WHERE id=?',(tid,)).fetchone(); con.close()
        if row and row[0]:
            name=str(row[0]); TYPE_NAME_RUNTIME_CACHE[tid]=name; return name
    except Exception:pass
    return None

def type_name(type_id):
    try:tid=int(type_id)
    except Exception:return 'Unresolved EVE type'
    return _local_type_name(tid) or f'Unresolved EVE type ({tid})'

def _fetch_type_from_esi(type_id):
    """Resolve one inventory type from CCP's public type endpoint.

    `/universe/names` does *not* resolve inventory type IDs.  Try both the
    rolling `latest` alias and the stable v3 route so type-name repair survives
    ESI compatibility/version transitions.
    """
    try:tid=int(type_id)
    except Exception:return None
    for path in (f'/latest/universe/types/{tid}/',f'/v3/universe/types/{tid}/'):
        try:
            data,_=esi_get_json(path,None,timeout=20,client_name='TypeNameResolver')
            name=str((data or {}).get('name') or '').strip()
            if not name:continue
            return (tid,name,(data or {}).get('group_id'),(data or {}).get('market_group_id'),(data or {}).get('volume'),1 if (data or {}).get('published',True) else 0)
        except Exception:
            continue
    return None

def ensure_type_names(type_ids):
    """Ensure ships, skills and item type IDs have readable EVE names.

    First uses the local SDE database. Missing entries are repaired from CCP's
    public `/universe/types/{type_id}` endpoint and cached locally. This makes
    name resolution work even if an older install has a damaged/incomplete SDE
    cache and avoids the incorrect `/universe/names` fallback used previously.
    """
    clean=[]; seen=set()
    for value in type_ids or []:
        try:tid=int(value or 0)
        except Exception:continue
        if tid>0 and tid not in seen and not _local_type_name(tid):
            seen.add(tid); clean.append(tid)
    if not clean:return 0

    rows=[]
    # Keep concurrency modest so a character with a large asset list does not
    # hammer ESI. Results are cached in SQLite, so each missing type normally
    # needs to be fetched only once.
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8,len(clean))) as pool:
        for rec in pool.map(_fetch_type_from_esi,clean):
            if not rec:continue
            rows.append(rec); TYPE_NAME_RUNTIME_CACHE[int(rec[0])]=str(rec[1])

    if rows and DB.exists():
        try:
            con=sqlite3.connect(DB,timeout=30)
            # Create the cache table defensively so name repair also works on a
            # legacy/partially-upgraded database instead of silently doing
            # nothing when the SDE update previously failed.
            con.execute('CREATE TABLE IF NOT EXISTS types(id INTEGER PRIMARY KEY,name TEXT COLLATE NOCASE,group_id INTEGER,market_group_id INTEGER,volume REAL,published INTEGER)')
            con.execute('CREATE INDEX IF NOT EXISTS ix_type_name ON types(name)')
            con.executemany('INSERT OR REPLACE INTO types(id,name,group_id,market_group_id,volume,published) VALUES(?,?,?,?,?,?)',rows)
            con.commit(); con.close()
        except Exception:
            pass
    return len(rows)

def skill_requirements(skill_type_id):
    try:tid=int(skill_type_id)
    except Exception:return []
    if not DB.exists():return []
    try:
        con=sqlite3.connect(DB); rows=con.execute('SELECT required_skill_id,required_level FROM skill_requirements WHERE skill_type_id=? ORDER BY required_skill_id',(tid,)).fetchall(); con.close(); return [(int(a),int(b)) for a,b in rows]
    except Exception:return []

def skill_meta(skill_type_id):
    try:tid=int(skill_type_id)
    except Exception:return None
    if not DB.exists():return None
    try:
        con=sqlite3.connect(DB); row=con.execute('SELECT rank,primary_attr,secondary_attr FROM skill_meta WHERE skill_type_id=?',(tid,)).fetchone(); con.close(); return row
    except Exception:return None

def type_search(query,limit=50):
    q=str(query or '').strip()
    if not q or not DB.exists():return []
    try:
        con=sqlite3.connect(DB)
        rows=con.execute('SELECT id,name,group_id,volume FROM types WHERE name LIKE ? ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END,name LIMIT ?',('%'+q+'%',q+'%',int(limit))).fetchall()
        con.close(); return rows
    except Exception:return []

def system_by_id(system_id):
    if not DB.exists():return None
    try:
        con=sqlite3.connect(DB)
        row=con.execute('SELECT s.id,s.name,s.x,s.y,s.z,s.security,s.region_id,COALESCE(r.name,"Unknown region"),COALESCE(s.station_count,0) FROM systems s LEFT JOIN regions r ON r.id=s.region_id WHERE s.id=?',(int(system_id),)).fetchone()
        con.close(); return row
    except Exception:return None

def stations_in_system(system_id):
    if not DB.exists():return []
    try:
        con=sqlite3.connect(DB)
        rows=con.execute('SELECT id,type_id,owner_name,operation_name,name FROM stations WHERE system_id=? ORDER BY owner_name,operation_name,id',(int(system_id),)).fetchall()
        con.close(); return rows
    except Exception:return []

def location_to_system(location_id):
    """Resolve a solar-system or NPC-station location ID to a local system row."""
    try: lid=int(location_id)
    except Exception:return None
    direct=system_by_id(lid)
    if direct:return direct
    if not DB.exists():return None
    try:
        con=sqlite3.connect(DB); r=con.execute('SELECT system_id FROM stations WHERE id=?',(lid,)).fetchone(); con.close()
        return system_by_id(r[0]) if r else None
    except Exception:return None

def location_label(location_id):
    try: lid=int(location_id)
    except Exception:return str(location_id or '—')
    sysrow=system_by_id(lid)
    if sysrow:return sysrow[1]
    if DB.exists():
        try:
            con=sqlite3.connect(DB); r=con.execute('SELECT system_id,owner_name,operation_name,name FROM stations WHERE id=?',(lid,)).fetchone(); con.close()
            if r:
                sr=system_by_id(r[0]); base=(r[3] or ' — '.join(x for x in (r[1],r[2]) if x) or f'NPC Station {lid}')
                return f'{base} ({sr[1] if sr else r[0]})'
        except Exception:pass
    return 'Unresolved location'

def gate_neighborhood(origin_name,max_hops=10):
    """Return systems reachable within N normal stargate hops from origin.

    The graph comes from CCP's SDE mapStargates table. Results include the
    origin at hop 0 and are returned as (system_row, hops).
    """
    origin=system(origin_name)
    if not origin or not DB.exists(): return origin,[]
    try:max_hops=max(1,min(30,int(max_hops)))
    except Exception:max_hops=10
    con=sqlite3.connect(DB)
    try:
        edges=con.execute('SELECT a,b FROM stargates').fetchall()
        rows=con.execute('SELECT s.id,s.name,s.x,s.y,s.z,s.security,s.region_id,COALESCE(r.name,"Unknown region"),COALESCE(s.station_count,0) FROM systems s LEFT JOIN regions r ON r.id=s.region_id').fetchall()
    finally: con.close()
    nodes={int(r[0]):r for r in rows}; adj={}
    for a,b in edges:
        a=int(a); b=int(b); adj.setdefault(a,[]).append(b); adj.setdefault(b,[]).append(a)
    seen={int(origin[0]):0}; q=deque([int(origin[0])])
    while q:
        sid=q.popleft(); h=seen[sid]
        if h>=max_hops: continue
        for nxt in adj.get(sid,()):
            if nxt in seen: continue
            seen[nxt]=h+1; q.append(nxt)
    out=[(nodes[sid],h) for sid,h in seen.items() if sid in nodes]
    out.sort(key=lambda x:(x[1],x[0][1].casefold()))
    return origin,out

def gate_shortest_path(start_name,dest_name,max_hops=80):
    start=system(start_name); dest=system(dest_name)
    if not start or not dest or not DB.exists(): return None
    if start[0]==dest[0]: return [start]
    con=sqlite3.connect(DB)
    try: edges=con.execute('SELECT a,b FROM stargates').fetchall()
    finally: con.close()
    adj={}
    for a,b in edges:
        adj.setdefault(int(a),[]).append(int(b)); adj.setdefault(int(b),[]).append(int(a))
    parent={int(start[0]):None}; depth={int(start[0]):0}; q=deque([int(start[0])])
    found=False
    while q:
        sid=q.popleft()
        if depth[sid]>=max_hops: continue
        for nxt in adj.get(sid,()):
            if nxt in parent: continue
            parent[nxt]=sid; depth[nxt]=depth[sid]+1
            if nxt==int(dest[0]): found=True; q.clear(); break
            q.append(nxt)
    if not found:return None
    ids=[]; cur=int(dest[0])
    while cur is not None: ids.append(cur); cur=parent.get(cur)
    ids.reverse(); return [system_by_id(x) for x in ids if system_by_id(x)]

def fetch_hunting_intel():
    """Public CCP hunting inputs: last-hour jumps/kills + current sovereignty systems.

    CCP removed /sovereignty/map for compatibility dates on/after 2026-05-19.
    Hunting intel must remain useful even if the optional sovereignty feed is
    unavailable, so activity data is returned independently of sov data.
    """
    activity=fetch_public_activity(); sovereignty={}; sov_error=''
    try:
        sov,_=esi_get_json('/latest/sovereignty/systems',None,client_name='HuntingIntelClient')
        rows=sov if isinstance(sov,list) else ((sov or {}).get('systems',[]) if isinstance(sov,dict) else [])
        for row in rows:
            if not isinstance(row,dict):continue
            solar=row.get('solar_system') or row.get('solarsystem') or {}
            claim=(solar.get('claim') if isinstance(solar,dict) else {}) or {}
            alliance=row.get('alliance') or claim.get('alliance') or {}
            faction=row.get('faction') or claim.get('faction') or {}
            hub=row.get('sovereignty_hub') or row.get('sovereigntyhub') or {}
            sid=(row.get('system_id') or row.get('solar_system_id') or row.get('solarsystem_id') or
                 (solar.get('id') if isinstance(solar,dict) else 0) or (solar.get('system_id') if isinstance(solar,dict) else 0))
            try:sid=int(sid or 0)
            except Exception:continue
            if not sid:continue
            def _id(obj,*keys):
                if not isinstance(obj,dict):return 0
                for k in keys:
                    try:
                        if obj.get(k) is not None:return int(obj.get(k) or 0)
                    except Exception:pass
                return 0
            sovereignty[str(sid)]={
                'alliance_id': int(row.get('alliance_id') or _id(alliance,'id','alliance_id') or 0),
                'corporation_id': int(row.get('corporation_id') or _id(claim,'corporation_id') or 0),
                'faction_id': int(row.get('faction_id') or _id(faction,'id','faction_id') or 0),
                'hub_id': int(row.get('structure_id') or _id(hub,'id','structure_id') or 0),
            }
    except Exception as e:
        sov_error=str(e)
    return {'systems':activity.get('systems',{}),'sovereignty':sovereignty,'fetched_at':int(time.time()),'source':'CCP ESI system_kills + system_jumps + sovereignty/systems','sovereignty_error':sov_error}

def hunting_score(mode,rec,sec,has_sov=False,observed_main=0.0):
    rec=rec or {}; npc=int(rec.get('npc_kills',0) or 0); ship=int(rec.get('ship_kills',0) or 0); pod=int(rec.get('pod_kills',0) or 0); jumps=int(rec.get('ship_jumps',0) or 0)
    pvp=ship*28 + pod*42 + min(jumps,500)*0.35
    rat=npc*1.0 + min(jumps,500)*0.08
    ess=(npc*1.15 + min(jumps,300)*0.05) if (float(sec)<=0.0 and has_sov) else 0.0
    if observed_main>0: ess += min(1500.0,math.log10(max(1.0,observed_main))*120.0)
    mode=str(mode or 'Balanced Roam')
    if mode=='Ratter Hunt': raw=rat + pvp*0.28
    elif mode=='PvP Activity': raw=pvp + rat*0.12
    elif mode=='ESS Hunt': raw=ess*1.6 + pvp*0.18
    else: raw=rat*0.55 + pvp*0.75 + ess*0.35
    return int(max(0,min(999,round(raw))))

def format_isk_short(value):
    try:v=float(value or 0)
    except Exception:return '—'
    if v<=0:return '—'
    for n,s in ((1e12,'t'),(1e9,'b'),(1e6,'m'),(1e3,'k')):
        if abs(v)>=n:return f'{v/n:.2f}{s}'
    return f'{v:,.0f}'

def distance_ly(a,b): return math.sqrt((a[2]-b[2])**2+(a[3]-b[3])**2+(a[4]-b[4])**2)/LY_METERS

def security_band(sec):
    try: sec=float(sec)
    except (TypeError,ValueError): return 'Unknown'
    if sec>=HIGHSEC_THRESHOLD: return 'High-sec'
    if sec>0.0: return 'Low-sec'
    return 'Null-sec'

def ship_cyno_types(ship):
    """Return cyno field types the selected hull can jump to."""
    cls=str(ship.get('class',''))
    if cls=='Black Ops': return ('Covert','Industrial','Standard')
    if ship.get('jf_bonus') or cls=='Capital Industrial': return ('Industrial','Standard')
    return ('Standard',)

def preferred_cyno_type(ship, live_jammed=False):
    types=ship_cyno_types(ship)
    if live_jammed and 'Covert' in types: return 'Covert'
    if ship.get('jf_bonus') or ship.get('class')=='Capital Industrial':
        return 'Industrial' if 'Industrial' in types else types[0]
    if ship.get('class')=='Black Ops': return 'Covert'
    return 'Standard'

def origin_legality(node, ship):
    """Static rules for whether this hull can normally begin a jump here.

    High-sec is allowed as an origin for Jump Freighters and Black Ops; neither
    can jump *into* high-sec because a destination cyno cannot be lit there.
    Pochven is permitted as an origin because trapped capitals may jump out.
    """
    if not node: return False,'System not found'
    name=str(node[1]); region=str(node[7])
    if name.casefold()=='zarzakh':
        return False,'Jump drives cannot be used from Zarzakh'
    if float(node[5])>=HIGHSEC_THRESHOLD:
        cls=str(ship.get('class',''))
        if not (ship.get('jf_bonus') or cls=='Black Ops'):
            return False,'True capital ships cannot normally operate from high-sec'
    return True,'Origin permitted'

def destination_legality(node, ship, incursion_systems=None, use_live=True):
    """Check destination legality and return (legal, cyno_type, reason).

    This enforces route-level rules knowable from public/static data.  Grid-local
    inhibitors and active sovereignty jammers still need an in-client check.
    """
    if not node: return False,'—','System not found'
    name=str(node[1]); region=str(node[7]); sec=float(node[5]); sid=int(node[0])
    if sec>=HIGHSEC_THRESHOLD:
        return False,'—','High-sec: cynos cannot be lit for jump-drive arrivals'
    if region.casefold()=='pochven':
        return False,'—','Pochven: region-wide cyno jamming prevents jump-drive entry'
    if name.casefold()=='zarzakh':
        return False,'—','Zarzakh does not support normal jump-drive travel'
    jammed=bool(use_live and incursion_systems and sid in incursion_systems)
    if jammed:
        if 'Covert' in ship_cyno_types(ship):
            return True,'Covert','Incursion cyno jam: Black Ops can use a covert cyno'
        return False,'—','Active Sansha Incursion: standard/industrial cynos are jammed'
    cyno=preferred_cyno_type(ship,False)
    if cyno=='Standard':
        return True,'Standard','Static rules allow a standard cyno / Pharolux beacon'
    return True,cyno,f'Static rules allow {cyno.lower()} or standard cyno'

def fetch_live_jump_restrictions():
    """Fetch public CCP ESI restrictions we can verify without EVE SSO.

    Active Sansha Incursion systems are cyno-jammed. Covert cynos remain usable,
    which means Black Ops can still route to them. Sovereignty jammer online
    state is not exposed reliably enough here, so it is deliberately not guessed.
    """
    query=urllib.parse.urlencode({'datasource':'tranquility'})
    url=f'{ESI_BASE}/incursions/?{query}'
    req=urllib.request.Request(url,headers={
        'User-Agent':f'{APP_NAME}/{VERSION} JumpLegalityClient',
        'Accept':'application/json',
        'X-Compatibility-Date':esi_compatibility_date(),
    })
    with urllib.request.urlopen(req,timeout=30) as r:
        incursions=json.load(r)
    systems=set()
    for inc in incursions if isinstance(incursions,list) else []:
        for sid in inc.get('infested_solar_systems',[]) or []:
            try: systems.add(int(sid))
            except (TypeError,ValueError): pass
    return {'incursion_systems':sorted(systems),'fetched_at':int(time.time()),'source':'CCP ESI /incursions/'}

def systems_in_range(origin_name,max_range):
    origin=system(origin_name)
    if not origin or not DB.exists(): return origin,[]
    radius=max_range*LY_METERS
    con=sqlite3.connect(DB)
    sql='SELECT s.id,s.name,s.x,s.y,s.z,s.security,s.region_id,COALESCE(r.name,"Unknown region"),COALESCE(s.station_count,0) FROM systems s LEFT JOIN regions r ON r.id=s.region_id WHERE s.id<>? AND s.x BETWEEN ? AND ? AND s.y BETWEEN ? AND ? AND s.z BETWEEN ? AND ?'
    rows=con.execute(sql,(origin[0],origin[2]-radius,origin[2]+radius,origin[3]-radius,origin[3]+radius,origin[4]-radius,origin[4]+radius)).fetchall()
    con.close()
    out=[]
    for r in rows:
        d=distance_ly(origin,r)
        if d<=max_range+1e-9: out.append((r[1],r[7],d,r[5],int(r[8] or 0)))
    out.sort(key=lambda x:x[2])
    return origin,out

def route_path(start_name, dest_name, max_range, security_mode='Low + Null', mode='Fewest Jumps', avoided_systems=None, avoided_regions=None, ship=None, enforce_legality=True, incursion_systems=None, use_live=True, station_policy='Any systems'):
    # Find one jump-drive route. mode is Fewest Jumps or Shortest Distance.
    start=system(start_name); dest=system(dest_name)
    if not start or not dest: return start,dest,None
    if start[0]==dest[0]: return start,dest,[start]
    ship=ship or {'class':'Unknown'}
    if enforce_legality:
        ok,_reason=origin_legality(start,ship)
        if not ok: return start,dest,None
        ok,_cyno,_reason=destination_legality(dest,ship,incursion_systems,use_live)
        if not ok: return start,dest,None
    avoided_systems={x.casefold() for x in (avoided_systems or []) if x.strip()}
    avoided_regions={x.casefold() for x in (avoided_regions or []) if x.strip()}
    if dest[1].casefold() in avoided_systems or dest[7].casefold() in avoided_regions:
        return start,dest,None
    station_policy=str(station_policy or 'Any systems')
    dest_stations=int(dest[8] or 0) if len(dest)>8 else 0
    if station_policy=='NPC stations only' and dest_stations<=0:
        return start,dest,None
    if station_policy=='Avoid NPC stations' and dest_stations>0:
        return start,dest,None
    radius=max_range*LY_METERS
    con=sqlite3.connect(DB)
    def allowed(node):
        sec=node[5]; name=node[1]; region=node[7]
        if name.casefold() in avoided_systems or region.casefold() in avoided_regions: return False
        if security_mode=='Low + Null' and sec>=HIGHSEC_THRESHOLD: return False
        if security_mode=='Null only' and sec>0.0: return False
        station_count=int(node[8] or 0) if len(node)>8 else 0
        if station_policy=='NPC stations only' and station_count<=0: return False
        if station_policy=='Avoid NPC stations' and station_count>0: return False
        if enforce_legality:
            legal,_cyno,_reason=destination_legality(node,ship,incursion_systems,use_live)
            if not legal: return False
        return True
    def neighbors(node):
        sql='SELECT s.id,s.name,s.x,s.y,s.z,s.security,s.region_id,COALESCE(r.name,"Unknown region"),COALESCE(s.station_count,0) FROM systems s LEFT JOIN regions r ON r.id=s.region_id WHERE s.id<>? AND s.x BETWEEN ? AND ? AND s.y BETWEEN ? AND ? AND s.z BETWEEN ? AND ?'
        rows=con.execute(sql,(node[0],node[2]-radius,node[2]+radius,node[3]-radius,node[3]+radius,node[4]-radius,node[4]+radius)).fetchall()
        out=[]
        for r in rows:
            if not allowed(r): continue
            d=distance_ly(node,r)
            if d<=max_range+1e-9: out.append((r,d))
        if station_policy=='Prefer NPC stations':
            out.sort(key=lambda x: (0 if (len(x[0])>8 and int(x[0][8] or 0)>0) else 1, distance_ly(x[0],dest)))
        else:
            out.sort(key=lambda x: distance_ly(x[0],dest))
        return out

    parent={start[0]:None}; nodes={start[0]:start}; found=False
    if mode=='Shortest Distance':
        import heapq
        costs={start[0]:0.0}; q=[(0.0,start[0])]
        while q and len(costs)<12000:
            cost,sid=heapq.heappop(q)
            if cost>costs.get(sid,float('inf'))+1e-12: continue
            cur=nodes[sid]
            if sid==dest[0]: found=True; break
            for nxt,d in neighbors(cur):
                station_penalty=(max_range*0.08) if (station_policy=='Prefer NPC stations' and not (len(nxt)>8 and int(nxt[8] or 0)>0)) else 0.0
                nc=cost+d+station_penalty
                if nc+1e-12 < costs.get(nxt[0],float('inf')):
                    costs[nxt[0]]=nc; parent[nxt[0]]=sid; nodes[nxt[0]]=nxt
                    heapq.heappush(q,(nc,nxt[0]))
    elif station_policy=='Prefer NPC stations':
        # Lexicographic station-aware routing: preserve the primary promise of
        # Fewest Jumps, then choose the route with the fewest non-station stops,
        # then the shortest total LY among otherwise-equal candidates.
        import heapq
        best={start[0]:(0,0,0.0)}
        q=[(0,0,0.0,start[0])]
        while q and len(best)<12000:
            hops,nonstations,ly,sid=heapq.heappop(q)
            if (hops,nonstations,ly)!=best.get(sid): continue
            cur=nodes[sid]
            if sid==dest[0]: found=True; break
            for nxt,d in neighbors(cur):
                is_station=(len(nxt)>8 and int(nxt[8] or 0)>0)
                score=(hops+1,nonstations+(0 if is_station else 1),ly+d)
                if score < best.get(nxt[0],(10**9,10**9,float('inf'))):
                    best[nxt[0]]=score; parent[nxt[0]]=sid; nodes[nxt[0]]=nxt
                    heapq.heappush(q,(score[0],score[1],score[2],nxt[0]))
    else:
        from collections import deque
        q=deque([start])
        while q and len(parent)<12000:
            cur=q.popleft()
            for nxt,d in neighbors(cur):
                if nxt[0] in parent: continue
                parent[nxt[0]]=cur[0]; nodes[nxt[0]]=nxt
                if nxt[0]==dest[0]: found=True; q.clear(); break
                q.append(nxt)
    con.close()
    if dest[0] in parent: found=True
    if not found: return start,dest,None
    ids=[]; x=dest[0]
    while x is not None:
        ids.append(x); x=parent[x]
    ids.reverse()
    return start,dest,[nodes.get(i, dest if i==dest[0] else start) for i in ids]

def calc_fuel(dist,ship,jfc,jf):
    # EVE modifiers are reductions from base requirement; round up to whole isotope units.
    jf_mod=(1-0.10*jf) if ship.get('jf_bonus') else 1.0
    return math.ceil(dist*ship['fuel']*(1-0.10*jfc)*jf_mod)


class AutoCompleteEntry(ttk.Entry):
    """System-name entry with a live dropdown backed by the local EVE database."""
    def __init__(self, master, textvariable, **kwargs):
        super().__init__(master, textvariable=textvariable, **kwargs)
        self.var=textvariable; self.popup=None; self.listbox=None; self.matches=[]
        self.bind('<KeyRelease>', self._changed)
        self.bind('<Down>', self._down)
        self.bind('<Up>', self._up)
        self.bind('<Return>', self._accept)
        self.bind('<Tab>', self._tab)
        self.bind('<Escape>', lambda e:self._hide())
        self.bind('<FocusOut>', lambda e:self.after(120,self._hide_if_focus_lost))
    def _changed(self,event=None):
        if event and event.keysym in ('Up','Down','Return','Tab','Escape','Left','Right','Home','End'): return
        q=self.var.get().strip()
        if not q: self._hide(); return
        self.matches=suggestions(q,10)
        if not self.matches: self._hide(); return
        self._show()
    def _show(self):
        if self.popup is None or not self.popup.winfo_exists():
            self.popup=tk.Toplevel(self); self.popup.overrideredirect(True); self.popup.attributes('-topmost',True)
            frame=ttk.Frame(self.popup,relief='solid',borderwidth=1); frame.pack(fill='both',expand=True)
            self.listbox=tk.Listbox(frame,height=min(10,len(self.matches)),activestyle='none',font=('Segoe UI',10),exportselection=False,bg='#0a121a',fg='#dce8ef',selectbackground='#174f6b',selectforeground='#ffffff',highlightthickness=0,relief='flat',bd=0)
            self.listbox.pack(fill='both',expand=True)
            self.listbox.bind('<ButtonRelease-1>',self._accept)
            self.listbox.bind('<Double-1>',self._accept)
            self.listbox.bind('<Return>',self._accept)
        self.listbox.delete(0,'end')
        for match in self.matches:
            name,region=match[0],match[1]
            station_count=int(match[2] or 0) if len(match)>2 else 0
            station_mark=f'   •   {station_count} NPC station'+('s' if station_count!=1 else '') if station_count else ''
            self.listbox.insert('end',f'{name} — {region}{station_mark}')
        self.listbox.config(height=min(10,len(self.matches)))
        self.update_idletasks(); x=self.winfo_rootx(); y=self.winfo_rooty()+self.winfo_height(); w=max(self.winfo_width(),220)
        self.popup.geometry(f'{w}x{min(230,24*len(self.matches)+4)}+{x}+{y}'); self.popup.deiconify(); self.popup.lift()
    def _down(self,event=None):
        if not self.matches: self._changed(); return 'break'
        if not self.popup or not self.popup.winfo_viewable(): self._show()
        cur=self.listbox.curselection(); idx=min((cur[0]+1 if cur else 0),len(self.matches)-1)
        self.listbox.selection_clear(0,'end'); self.listbox.selection_set(idx); self.listbox.see(idx); return 'break'
    def _up(self,event=None):
        if not self.matches: return 'break'
        cur=self.listbox.curselection(); idx=max((cur[0]-1 if cur else 0),0)
        self.listbox.selection_clear(0,'end'); self.listbox.selection_set(idx); self.listbox.see(idx); return 'break'
    def _accept(self,event=None):
        if not self.matches: return 'break'
        cur=self.listbox.curselection() if self.listbox else ()
        idx=cur[0] if cur else 0; self.var.set(self.matches[idx][0]); self.icursor('end'); self._hide(); self.focus_set(); return 'break'
    def _tab(self,event=None):
        if self.matches: return self._accept(event)
    def _hide_if_focus_lost(self):
        try:
            focus=self.focus_get()
            if focus is self or focus is self.listbox: return
        except: pass
        self._hide()
    def _hide(self):
        if self.popup and self.popup.winfo_exists(): self.popup.withdraw()


class HoverTip:
    """Small, dependency-free tooltip used by the compact navigation rail."""
    def __init__(self, widget, text):
        self.widget=widget; self.text=text; self.tip=None; self.after_id=None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')
    def _schedule(self,event=None):
        self._cancel(); self.after_id=self.widget.after(450,self._show)
    def _cancel(self):
        if self.after_id:
            try:self.widget.after_cancel(self.after_id)
            except Exception:pass
            self.after_id=None
    def _show(self):
        if self.tip or not self.text:return
        try:
            x=self.widget.winfo_rootx()+self.widget.winfo_width()+8
            y=self.widget.winfo_rooty()+max(2,self.widget.winfo_height()//2-12)
            self.tip=tk.Toplevel(self.widget); self.tip.overrideredirect(True); self.tip.attributes('-topmost',True)
            tk.Label(self.tip,text=self.text,bg='#102130',fg='#eaf8ff',font=('Segoe UI Semibold',9),
                     padx=9,pady=5,relief='solid',bd=1,highlightthickness=0).pack()
            self.tip.geometry(f'+{x}+{y}')
        except Exception:
            self.tip=None
    def _hide(self,event=None):
        self._cancel()
        if self.tip:
            try:self.tip.destroy()
            except Exception:pass
            self.tip=None

class ScrollablePage(ttk.Frame):
    """Notebook page that keeps all controls reachable at small window sizes."""
    def __init__(self, master, padding=12):
        super().__init__(master,style='TFrame')
        self.canvas=tk.Canvas(self,bg='#0b1118',highlightthickness=0,bd=0,relief='flat')
        self.vbar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.hbar=ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set,xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        self.vbar.grid(row=0,column=1,sticky='ns')
        self.hbar.grid(row=1,column=0,sticky='ew')
        self.rowconfigure(0,weight=1); self.columnconfigure(0,weight=1)
        self.body=ttk.Frame(self.canvas,padding=padding,style='TFrame')
        self.window_id=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self._sync_pending=False
        self.body.bind('<Configure>',self._schedule_sync,add='+')
        self.canvas.bind('<Configure>',self._schedule_sync,add='+')
        self._schedule_sync()
    def _schedule_sync(self,event=None):
        if self._sync_pending:return
        self._sync_pending=True
        self.after_idle(self._sync)
    def _sync(self):
        self._sync_pending=False
        try:
            self.update_idletasks()
            vw=max(1,self.canvas.winfo_width()); vh=max(1,self.canvas.winfo_height())
            rw=max(1,self.body.winfo_reqwidth()); rh=max(1,self.body.winfo_reqheight())
            width=max(vw,rw); height=max(vh,rh)
            self.canvas.itemconfigure(self.window_id,width=width,height=height)
            self.canvas.configure(scrollregion=(0,0,width,height))
            # Hide scrollbars when they are not needed, so full-size windows stay clean.
            if rh>vh+2:self.vbar.grid()
            else:
                self.vbar.grid_remove(); self.canvas.yview_moveto(0)
            if rw>vw+2:self.hbar.grid()
            else:
                self.hbar.grid_remove(); self.canvas.xview_moveto(0)
        except tk.TclError:
            pass
    def scroll_y(self,units):
        try:self.canvas.yview_scroll(int(units),'units')
        except Exception:pass
    def scroll_x(self,units):
        try:self.canvas.xview_scroll(int(units),'units')
        except Exception:pass

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(f'{APP_NAME} v{VERSION}'); self.geometry('1440x900'); self.minsize(760,560)
        try:
            icon=bundled_asset('assets/new_eden_command.ico')
            if icon.exists(): self.iconbitmap(default=str(icon))
        except Exception:
            pass
        self.configure(background='#070b10')
        style=ttk.Style(self); style.theme_use('clam')
        # EVE-inspired dark cockpit theme. Keep the accent restrained so data remains the focus.
        style.configure('.',background='#0b1118',foreground='#d8e2ea',fieldbackground='#111a24',font=('Segoe UI',10))
        style.configure('TFrame',background='#0b1118')
        style.configure('Hero.TFrame',background='#070b10')
        style.configure('TLabel',background='#0b1118',foreground='#d8e2ea')
        style.configure('Title.TLabel',background='#081018',foreground='#f4fbff',font=('Segoe UI Semibold',22))
        style.configure('Subtitle.TLabel',background='#081018',foreground='#78a9c6',font=('Segoe UI Semibold',9))
        style.configure('Chip.TLabel',background='#102637',foreground='#91e9ff',padding=(10,5),font=('Consolas',9,'bold'))
        style.configure('TLabelframe',background='#0b1118',foreground='#9fc8e6',bordercolor='#243343',relief='solid')
        style.configure('TLabelframe.Label',background='#0b1118',foreground='#9fc8e6',font=('Segoe UI Semibold',10))
        style.configure('TButton',background='#132333',foreground='#e9f4fb',bordercolor='#2b526d',padding=(10,7),font=('Segoe UI Semibold',9))
        style.map('TButton',background=[('active','#1d3143'),('pressed','#0d1924')],foreground=[('disabled','#5d6b77')])
        style.configure('Accent.TButton',background='#0879ad',foreground='#ffffff',bordercolor='#35c7ff',padding=(12,7),font=('Segoe UI Semibold',10))
        style.map('Accent.TButton',background=[('active','#1477a3'),('pressed','#0a4b69')])
        style.configure('TEntry',fieldbackground='#111a24',foreground='#e8eef3',insertcolor='#e8eef3',bordercolor='#31465a')
        style.configure('TCombobox',fieldbackground='#111a24',background='#111a24',foreground='#e8eef3',arrowcolor='#9fc8e6',bordercolor='#31465a')
        style.map('TCombobox',fieldbackground=[('readonly','#111a24')],foreground=[('readonly','#e8eef3')])
        style.configure('TNotebook',background='#070b10',borderwidth=0)
        style.configure('TNotebook.Tab',background='#101923',foreground='#91a2b1',padding=(14,8),borderwidth=0)
        style.map('TNotebook.Tab',background=[('selected','#152535'),('active','#12202d')],foreground=[('selected','#eaf5fb')])
        style.configure('Treeview',background='#0e1720',fieldbackground='#0e1720',foreground='#dbe5ec',rowheight=27,bordercolor='#243343')
        style.map('Treeview',background=[('selected','#164b68')],foreground=[('selected','#ffffff')])
        style.configure('Treeview.Heading',background='#15222e',foreground='#a9c4d6',font=('Segoe UI Semibold',9),relief='flat')
        style.map('Treeview.Heading',background=[('active','#1c3041')])
        style.configure('TCheckbutton',background='#0b1118',foreground='#cbd6de')
        style.configure('TProgressbar',background='#23b7e5',troughcolor='#0b1219',bordercolor='#213343',lightcolor='#23b7e5',darkcolor='#23b7e5')
        style.configure('TScrollbar',background='#142330',troughcolor='#081018',bordercolor='#081018',arrowcolor='#87a4b7')
        # v2 command-center surfaces and navigation
        style.configure('Sidebar.TFrame',background='#060a0f')
        style.configure('Topbar.TFrame',background='#081018')
        style.configure('Panel.TFrame',background='#0c1823',relief='flat')
        style.configure('Card.TFrame',background='#0d1c29',relief='solid',borderwidth=1)
        style.configure('CardTitle.TLabel',background='#0d1c29',foreground='#6ebbe4',font=('Segoe UI Semibold',8))
        style.configure('CardValue.TLabel',background='#0d1c29',foreground='#f4fbff',font=('Segoe UI Semibold',15))
        style.configure('SectionTitle.TLabel',background='#0b1118',foreground='#f0f7fb',font=('Segoe UI Semibold',17))
        style.configure('SectionSub.TLabel',background='#0b1118',foreground='#6f8799',font=('Segoe UI',9))
        style.configure('HUD.TLabel',background='#0b1118',foreground='#91a8ba',font=('Segoe UI',9))
        style.configure('PanelHUD.TLabel',background='#0d1620',foreground='#91a8ba',font=('Segoe UI Semibold',8))
        style.configure('Nav.TButton',background='#060a0f',foreground='#8aa8ba',borderwidth=0,padding=(13,11),anchor='w',font=('Segoe UI Semibold',10))
        style.map('Nav.TButton',background=[('active','#0d1822')],foreground=[('active','#dbeaf3')])
        style.configure('NavActive.TButton',background='#0e3a56',foreground='#9cecff',borderwidth=0,padding=(13,11),anchor='w',font=('Segoe UI Semibold',10))
        style.map('NavActive.TButton',background=[('active','#15384d')],foreground=[('active','#ffffff')])
        style.configure('NavCompact.TButton',background='#060a0f',foreground='#8aa8ba',borderwidth=0,padding=(0,11),anchor='center',font=('Segoe UI Symbol',13))
        style.map('NavCompact.TButton',background=[('active','#0d1822')],foreground=[('active','#dff8ff')])
        style.configure('NavCompactActive.TButton',background='#0e3a56',foreground='#9cecff',borderwidth=0,padding=(0,11),anchor='center',font=('Segoe UI Symbol',13))
        style.map('NavCompactActive.TButton',background=[('active','#155277')],foreground=[('active','#ffffff')])
        style.configure('Ghost.TButton',background='#0d1620',foreground='#9fb3c2',bordercolor='#223442',padding=(10,7))
        style.configure('Danger.TButton',background='#32171b',foreground='#ffc1c5',bordercolor='#6d2b33',padding=(10,7))
        style.configure('Command.TNotebook',background='#070b10',borderwidth=0)
        style.layout('Command.TNotebook.Tab', [])
        # Native combobox pop-downs otherwise keep a bright Windows listbox.
        self.option_add('*TCombobox*Listbox.background','#0a121a')
        self.option_add('*TCombobox*Listbox.foreground','#dce8ef')
        self.option_add('*TCombobox*Listbox.selectBackground','#174f6b')
        self.option_add('*TCombobox*Listbox.selectForeground','#ffffff')
        self.status=tk.StringVar(value='Ready')
        self.update_detail=tk.StringVar(value='EVE data updater ready')
        self.update_percent=tk.StringVar(value='0%')
        self.update_progress=tk.DoubleVar(value=0)
        self.update_window=None
        self.update_dialog_detail=None
        self.update_dialog_percent=None
        self.update_dialog_progress=None
        self.update_dialog_close=None
        self.update_running=False
        self.config=load_config()
        self.favorite_systems=[]
        for fav in self.config.get('favorite_systems',[]):
            name=str(fav).strip()
            if name and name.casefold() not in {x.casefold() for x in self.favorite_systems}: self.favorite_systems.append(name)
        recent=self.config.get('recent_routes',[])
        self.recent_routes=[x for x in recent if isinstance(x,dict)][:20] if isinstance(recent,list) else []
        self.dashboard_pilot=tk.StringVar(value='No EVE character selected')
        self.dashboard_ship=tk.StringVar(value='')
        self.dashboard_fuel=tk.StringVar(value='')
        self.dashboard_data=tk.StringVar(value='EVE data: checking…')
        self.dashboard_market=tk.StringVar(value='Jita fuel: checking…')
        self.quick_from=tk.StringVar()
        self.quick_to=tk.StringVar()
        self.favorite_tree=None
        self.recent_route_tree=None
        state=self.config.get('app_state',{})
        market_cache=self.config.get('market_prices',{}) if isinstance(self.config.get('market_prices',{}),dict) else {}
        cached_sell=market_cache.get('sell',{}) if isinstance(market_cache.get('sell',{}),dict) else {}
        cached_buy=market_cache.get('buy',{}) if isinstance(market_cache.get('buy',{}),dict) else {}
        saved_prices=cached_sell or self.config.get('fuel_prices',{})
        self.fuel_price_vars={name:tk.StringVar(value=str(saved_prices.get(name,''))) for name in ('Helium Isotopes','Hydrogen Isotopes','Nitrogen Isotopes','Oxygen Isotopes')}
        self.market_buy_vars={name:tk.StringVar(value=('' if cached_buy.get(name) is None else str(cached_buy.get(name,'')))) for name in ('Helium Isotopes','Hydrogen Isotopes','Nitrogen Isotopes','Oxygen Isotopes')}
        self.price_status=tk.StringVar(value='Jita prices will refresh automatically from CCP ESI. Fuel cost uses the lowest Jita 4-4 sell order.')
        self.market_refresh_running=False
        self.price_refresh_btn=None
        live_cache=self.config.get('live_jump_restrictions',{}) if isinstance(self.config.get('live_jump_restrictions',{}),dict) else {}
        self.incursion_systems={int(x) for x in live_cache.get('incursion_systems',[]) if str(x).isdigit()}
        self.live_rules_status=tk.StringVar(value='Live restrictions: using cached CCP ESI data.' if self.incursion_systems else 'Live restrictions: not refreshed yet.')
        self.live_rules_running=False
        self.range_legal_only=tk.BooleanVar(value=True)
        self.range_station_filter=tk.StringVar(value=str(state.get('range_station_filter','All systems')))
        if self.range_station_filter.get() not in ('All systems','NPC station systems','No NPC stations'): self.range_station_filter.set('All systems')
        self.enforce_legality=tk.BooleanVar(value=True)
        self.route_station_policy=tk.StringVar(value=str(state.get('route_station_policy','Any systems')))
        if self.route_station_policy.get() not in ('Any systems','Prefer NPC stations','NPC stations only','Avoid NPC stations'): self.route_station_policy.set('Any systems')
        self.route_require_dest_station=tk.BooleanVar(value=bool(state.get('route_require_dest_station',False)))
        self.route_metric_jumps=tk.StringVar(value='—')
        self.route_metric_ly=tk.StringVar(value='—')
        self.route_metric_fuel=tk.StringVar(value='—')
        self.route_metric_cost=tk.StringVar(value='—')
        self.route_metric_stations=tk.StringVar(value='—')
        self.use_live_rules=tk.BooleanVar(value=True)
        self.update_package_path=tk.StringVar()
        self.update_feed_url=tk.StringVar(value=str(self.config.get('update_feed_url','')))
        self.app_update_status=tk.StringVar(value=f'Running {APP_NAME} v{VERSION}. Application updates preserve your CCP data, saved routes and settings.')
        self.app_update_progress=tk.DoubleVar(value=0)
        self.app_update_percent=tk.StringVar(value='')
        self.online_update_feed=None
        self.online_check_running=False
        self.online_download_running=False
        self.online_download_btn=None
        self.online_check_btn=None
        self.pending_update_arg=self.command_line_update_path()
        self.last_route_export_rows=[]
        self.last_route_summary=''
        self.last_route_nodes=[]
        self.route_map_zoom=1.0
        self.route_map_selected_index=None
        self.route_map_hitboxes=[]
        self.route_map_redraw_after=None
        self.route_map_show_labels=tk.BooleanVar(value=True)
        self.route_map_show_regions=tk.BooleanVar(value=False)
        self.route_map_show_stations=tk.BooleanVar(value=True)
        self.route_map_show_radius=tk.BooleanVar(value=True)
        self.route_map_status=tk.StringVar(value='Calculate a route to display its SDE-coordinate map.')
        sso_cfg=self.config.get('esi_sso',{}) if isinstance(self.config.get('esi_sso',{}),dict) else {}
        self.esi_auto_apply=tk.BooleanVar(value=bool(sso_cfg.get('auto_apply',True)))
        self.esi_character_id=int(sso_cfg.get('active_character_id',0) or 0)
        chars=sso_cfg.get('characters',{}) if isinstance(sso_cfg.get('characters',{}),dict) else {}
        active_rec=chars.get(str(self.esi_character_id),{}) if self.esi_character_id else {}
        active_name=str(active_rec.get('character_name','')).strip()
        self.esi_character_name=tk.StringVar(value=active_name or 'No character selected')
        self.esi_character_status=tk.StringVar(value='Add an EVE character or select one already connected on this PC.')
        self.esi_skills_status=tk.StringVar(value='Select a character to view and apply its jump skills.')
        cached_skills=active_rec.get('skills',{}) if isinstance(active_rec.get('skills',{}),dict) else {}
        self.esi_skill_vars={name:tk.StringVar(value=str(cached_skills.get(name,'—'))) for name in CHARACTER_SKILLS}
        self.esi_sso_running=False
        self.esi_connect_btn=None
        self.esi_refresh_btn=None
        self.esi_refresh_all_btn=None
        self.esi_use_btn=None
        self.esi_remove_btn=None
        self.esi_character_tree=None
        self.esi_permission_btn=None
        self.system_context_menu=None
        self.context_system_name=''
        self.in_game_action_running=False
        ship_name=normalize_ship_name(state.get('ship','Rhea'))
        self.ship=tk.StringVar(value=ship_name); self.jdc=tk.IntVar(value=int(state.get('jdc',5))); self.jfc=tk.IntVar(value=int(state.get('jfc',5))); self.jf=tk.IntVar(value=int(state.get('jf',5)))
        self.frm=tk.StringVar(); self.to=tk.StringVar()
        self.waypoints=[]; self.avoided_systems=[]
        self.profile_name=tk.StringVar(); self.saved_route_name=tk.StringVar()
        # v3 command-center, asset, intel and capital-operation state.
        self.companion_sync_running=False
        self.command_status=tk.StringVar(value='Connect/re-authorize characters, then sync live ESI data.')
        self.command_metric_location=tk.StringVar(value='—')
        self.command_metric_ship=tk.StringVar(value='—')
        self.command_metric_wallet=tk.StringVar(value='—')
        self.command_metric_online=tk.StringVar(value='—')
        self.asset_search_var=tk.StringVar()
        self.asset_exclude_fitted_var=tk.BooleanVar(value=True)
        self.asset_status=tk.StringVar(value='Sync character data to search assets across pilots.')
        self.asset_value_status=tk.StringVar(value='Asset valuation uses CCP market average prices with adjusted-price fallback.')
        self.asset_selected_summary=tk.StringVar(value='Select a system to inspect its assets.')
        self.asset_price_cache=load_asset_market_price_cache()
        self.asset_price_refresh_running=False
        self.asset_system_tree=None; self.asset_tree=None; self.asset_group_rows={}; self.asset_row_meta={}
        self.command_char_tree=None; self.alert_tree=None; self.contract_tree=None; self.contract_trees={}; self.contract_items_tree=None; self.contract_detail_var=tk.StringVar(value='Select a contract to view details and item names.'); self.industry_tree=None; self.skillqueue_tree=None
        # Cache the expensive Command Center render. Large asset inventories can contain
        # tens of thousands of rows, so rebuilding them on every tab switch made the UI
        # feel much slower than the underlying cached ESI data actually is.
        self._command_center_snapshot_signature=None
        self.skillplan_character=tk.StringVar(value='Active character')
        self.skillplan_status=tk.StringVar(value='Import a synced EVE queue, then optimise it shortest-first while preserving prerequisites.')
        self.skillplan_summary=tk.StringVar(value='No queue imported.')
        self.skillplan_tree=None; self.skillplan_rows=[]; self.skillplan_original=[]
        self.operations=self.config.get('operations',{}) if isinstance(self.config.get('operations',{}),dict) else {}
        self.active_operation_name=str(self.config.get('active_operation','') or '')
        self.operation_name=tk.StringVar(value=self.active_operation_name)
        self.operation_status=tk.StringVar(value='Create an operation from a calculated route.')
        self.operation_fuel_summary=tk.StringVar(value='No operation loaded.')
        self.operation_next_summary=tk.StringVar(value='NEXT JUMP —')
        self.operation_route_tree=None; self.operation_manifest_tree=None; self.operation_compare_tree=None
        self.operation_qty=tk.IntVar(value=1)
        self.operation_pilot=tk.StringVar(value='Active character')
        self.operation_note=tk.StringVar()
        self.activity_data=self.config.get('activity_cache',{}) if isinstance(self.config.get('activity_cache',{}),dict) else {}
        self.activity_refresh_running=False
        self.activity_status=tk.StringVar(value='Activity intel uses CCP ESI last-hour jumps and kills.')
        self.hunting_data=self.config.get('hunting_cache',{}) if isinstance(self.config.get('hunting_cache',{}),dict) else {}
        self.hunting_refresh_running=False
        self.hunt_origin=tk.StringVar(value=str(state.get('hunt_origin','')))
        self.hunt_max_hops=tk.IntVar(value=max(1,min(30,int(state.get('hunt_max_hops',10) or 10))))
        self.hunt_security=tk.StringVar(value=str(state.get('hunt_security','Low + Null')))
        if self.hunt_security.get() not in ('All k-space','Low + Null','Null only'): self.hunt_security.set('Low + Null')
        self.hunt_mode=tk.StringVar(value=str(state.get('hunt_mode','Ratter Hunt')))
        if self.hunt_mode.get() not in ('Ratter Hunt','PvP Activity','ESS Hunt','Balanced Roam'): self.hunt_mode.set('Ratter Hunt')
        self.hunt_min_npc=tk.IntVar(value=max(0,int(state.get('hunt_min_npc',0) or 0)))
        self.hunt_status=tk.StringVar(value='Choose an origin and scan nearby stargate space. Exact pilots-in-space and ESS balances are not public ESI data.')
        self.hunt_metric_systems=tk.StringVar(value='—'); self.hunt_metric_ratting=tk.StringVar(value='—'); self.hunt_metric_pvp=tk.StringVar(value='—'); self.hunt_metric_ess=tk.StringVar(value='—')
        self.hunt_tree=None; self.hunt_results=[]
        self.ess_observations=self.config.get('ess_observations',{}) if isinstance(self.config.get('ess_observations',{}),dict) else {}
        self.build_ui(); self.update_ship_controls(); self.protocol('WM_DELETE_WINDOW',self.on_close); self.after(200,self.startup)
        if self.pending_update_arg:
            self.after(450,self.handle_command_line_update)
    def build_ui(self):
        # v3.4.6 shell — responsive command interface with DPI-safe navigation
        # rail and scrollable pages.  The inner tools remain the same; the shell
        # now adapts rather than clipping controls when Windows is resized.
        shell=ttk.Frame(self,style='Hero.TFrame'); shell.pack(fill='both',expand=True)
        self.shell=shell
        # Size the expanded rail from the rendered navigation font instead of a fixed
        # pixel width.  Fixed widths clip labels on Windows when display scaling is
        # 125%/150% even though the same layout is fine at 100%.
        nav_labels=('Flight Deck','Command Center','Hunting','Capital Ops','Skill Planner',
                    'Jump Calculator','Systems in Range','Route Planner','Characters',
                    'Jita Fuel','Saved Routes','Update Center')
        try:
            from tkinter import font as tkfont
            nav_font=tkfont.Font(self,font=('Segoe UI Semibold',10))
            longest=max(nav_font.measure(f'◎   {label}') for label in nav_labels)
            self.sidebar_expanded_width=max(238,longest+62)
        except Exception:
            self.sidebar_expanded_width=258
        sidebar=ttk.Frame(shell,style='Sidebar.TFrame',width=self.sidebar_expanded_width); sidebar.pack(side='left',fill='y'); sidebar.pack_propagate(False)
        self.sidebar=sidebar
        main=ttk.Frame(shell,style='Hero.TFrame'); main.pack(side='left',fill='both',expand=True)
        self.main_shell=main

        brand=ttk.Frame(sidebar,style='Sidebar.TFrame',padding=(14,16,10,14)); brand.pack(fill='x')
        self.brand_frame=brand
        self.brand_logo_full=None; self.brand_logo_compact=None
        try:
            lp=bundled_asset('assets/new_eden_command_64.png')
            cp=bundled_asset('assets/new_eden_command_40.png')
            if lp.exists(): self.brand_logo_full=tk.PhotoImage(file=str(lp))
            if cp.exists(): self.brand_logo_compact=tk.PhotoImage(file=str(cp))
        except Exception:
            pass
        self.brand_logo_label=tk.Label(brand,bg='#060a0f',bd=0,highlightthickness=0)
        if self.brand_logo_full:self.brand_logo_label.configure(image=self.brand_logo_full)
        else:self.brand_logo_label.configure(text='NEC',fg='#8ee5ff',font=('Segoe UI Semibold',18))
        self.brand_logo_label.grid(row=0,column=0,rowspan=2,sticky='w',padx=(0,10))
        self.brand_name_label=tk.Label(brand,text='NEW EDEN',bg='#060a0f',fg='#edf9ff',font=('Segoe UI Semibold',12),anchor='w')
        self.brand_name_label.grid(row=0,column=1,sticky='sw')
        self.brand_sub_label=tk.Label(brand,text='COMMAND',bg='#060a0f',fg='#7dd3fc',font=('Segoe UI Semibold',9),anchor='w')
        self.brand_sub_label.grid(row=1,column=1,sticky='nw')
        brand.columnconfigure(1,weight=1)
        self.sidebar_rule=tk.Frame(sidebar,bg='#17354a',height=1); self.sidebar_rule.pack(fill='x',padx=14,pady=(0,10))
        self.nav_host=ttk.Frame(sidebar,style='Sidebar.TFrame'); self.nav_host.pack(fill='x')
        self.nav_buttons={}; self.nav_button_meta={}; self.nav_tips=[]
        self.sidebar_live_label=tk.Label(sidebar,text='NEW EDEN AWAITS',bg='#060a0f',fg='#3f6f88',font=('Segoe UI Semibold',8))
        self.sidebar_live_label.pack(side='bottom',anchor='w',padx=16,pady=(0,2))
        self.sidebar_build_label=tk.Label(sidebar,text=f'v{VERSION}  •  ONLINE',bg='#060a0f',fg='#5f8398',font=('Consolas',8))
        self.sidebar_build_label.pack(side='bottom',anchor='w',padx=16,pady=(0,14))

        root=ttk.Frame(main,padding=(18,12,18,10),style='Hero.TFrame'); root.pack(fill='both',expand=True)
        self.root_shell=root
        hero=ttk.Frame(root,style='Topbar.TFrame',padding=(16,11)); hero.pack(fill='x',pady=(0,8)); hero.columnconfigure(0,weight=1)
        self.hero=hero
        titlebox=ttk.Frame(hero,style='Topbar.TFrame'); titlebox.grid(row=0,column=0,sticky='w')
        self.hero_title=ttk.Label(titlebox,text='NEW EDEN COMMAND',style='Title.TLabel'); self.hero_title.pack(anchor='w')
        self.hero_subtitle=ttk.Label(titlebox,text='NAVIGATE  •  PLAN  •  OPERATE  •  CAPITAL LOGISTICS  •  EVE CLIENT BRIDGE',style='Subtitle.TLabel')
        self.hero_subtitle.pack(anchor='w',pady=(2,0))
        self.version_chip=ttk.Label(hero,text=f'ONLINE  //  v{VERSION}',style='Chip.TLabel'); self.version_chip.grid(row=0,column=1,sticky='e',padx=(12,0))

        box=ttk.Frame(root,style='Panel.TFrame',padding=(12,9)); box.pack(fill='x')
        self.hud_box=box
        fields=ttk.Frame(box,style='Panel.TFrame'); fields.pack(fill='x')
        self.hud_fields=fields
        self.hud_groups=[]
        def hud_group(title,widget_factory):
            g=ttk.Frame(fields,style='Panel.TFrame')
            lab=ttk.Label(g,text=title,style='PanelHUD.TLabel'); lab.pack(anchor='w',pady=(0,3))
            widget=widget_factory(g); widget.pack(fill='x')
            self.hud_groups.append(g)
            return g,lab,widget
        g,self.ship_label,self.ship_combo=hud_group('ACTIVE HULL',lambda m:ttk.Combobox(m,textvariable=self.ship,values=list(SHIPS),state='readonly'))
        self.ship_combo.bind('<<ComboboxSelected>>',lambda e:self.update_ship_controls())
        g,self.jdc_label,self.jdc_combo=hud_group('JUMP DRIVE CALIBRATION',lambda m:ttk.Combobox(m,textvariable=self.jdc,values=list(range(6)),state='readonly'))
        g,self.jfc_label,self.jfc_combo=hud_group('JUMP FUEL CONSERVATION',lambda m:ttk.Combobox(m,textvariable=self.jfc,values=list(range(6)),state='readonly'))
        g,self.jf_label,self.jf_combo=hud_group('JUMP FREIGHTERS',lambda m:ttk.Combobox(m,textvariable=self.jf,values=list(range(6)),state='readonly'))
        rg=ttk.Frame(fields,style='Panel.TFrame'); ttk.Label(rg,text='DATA FEEDS',style='PanelHUD.TLabel').pack(anchor='w',pady=(0,3))
        self.refresh_data_btn=ttk.Button(rg,text='REFRESH DATA',command=self.do_update,style='Ghost.TButton'); self.refresh_data_btn.pack(fill='x')
        self.hud_groups.append(rg)
        self._layout_hud_groups(1200)

        self.tabs=ttk.Notebook(root,style='Command.TNotebook'); self.tabs.pack(fill='both',expand=True,pady=(8,0))
        dashboard_page=ScrollablePage(self.tabs,padding=12); dashboard=dashboard_page.body
        command_page=ScrollablePage(self.tabs,padding=12); command=command_page.body
        hunting_page=ScrollablePage(self.tabs,padding=12); hunting=hunting_page.body
        operations_page=ScrollablePage(self.tabs,padding=12); operations=operations_page.body
        skillplanner_page=ScrollablePage(self.tabs,padding=12); skillplanner=skillplanner_page.body
        jump_page=ScrollablePage(self.tabs,padding=12); jump=jump_page.body
        reach_page=ScrollablePage(self.tabs,padding=12); reach=reach_page.body
        planner_page=ScrollablePage(self.tabs,padding=12); planner=planner_page.body
        character_page=ScrollablePage(self.tabs,padding=12); character=character_page.body
        prices_page=ScrollablePage(self.tabs,padding=12); prices=prices_page.body
        saved_page=ScrollablePage(self.tabs,padding=12); saved=saved_page.body
        updates_page=ScrollablePage(self.tabs,padding=12); updates=updates_page.body
        self.dashboard_tab=dashboard_page; self.command_tab=command_page; self.hunting_tab=hunting_page; self.operations_tab=operations_page; self.skillplanner_tab=skillplanner_page; self.jump_tab=jump_page; self.range_tab=reach_page; self.planner_tab=planner_page; self.updates_tab=updates_page; self.character_tab=character_page
        self.page_scrolls={str(p):p for p in (dashboard_page,command_page,hunting_page,operations_page,skillplanner_page,jump_page,reach_page,planner_page,character_page,prices_page,saved_page,updates_page)}
        page_specs=[
            (dashboard_page,'Flight Deck','◆'),(command_page,'Command Center','⌘'),(hunting_page,'Hunting','✧'),(operations_page,'Capital Ops','⚑'),(skillplanner_page,'Skill Planner','✦'),
            (jump_page,'Jump Calculator','↗'),(reach_page,'Systems in Range','◎'),(planner_page,'Route Planner','◇'),
            (character_page,'Characters','●'),(prices_page,'Jita Fuel','◈'),(saved_page,'Saved Routes','▣'),(updates_page,'Update Center','⇧')
        ]
        for page,label,glyph in page_specs:
            self.tabs.add(page,text=label)
            b=ttk.Button(self.nav_host,text=f'{glyph}   {label}',style='Nav.TButton',command=lambda p=page:self.tabs.select(p))
            b.pack(fill='x',padx=8,pady=1); self.nav_buttons[str(page)]=b
            self.nav_button_meta[str(page)]=(glyph,label)
            self.nav_tips.append(HoverTip(b,label))
        self.tabs.bind('<<NotebookTabChanged>>',self._on_tab_changed)
        self.bind_all('<MouseWheel>',self._on_global_mousewheel,add='+')
        self.bind('<Configure>',self._on_window_configure,add='+')
        self.after_idle(self._on_tab_changed)
        self.after_idle(self._apply_responsive_layout)

        # Flight Deck: a compact operational overview for the pilot, current hull,
        # favorite systems and recent jump routes.
        deck_head=ttk.Frame(dashboard); deck_head.pack(fill='x',pady=(0,10)); deck_head.columnconfigure(0,weight=1)
        ttk.Label(deck_head,text='FLIGHT DECK',font=('Segoe UI Semibold',18)).grid(row=0,column=0,sticky='w')
        ttk.Label(deck_head,text='Pilot, ship, fuel and navigation at a glance',foreground='#8193a4').grid(row=1,column=0,sticky='w')
        ttk.Button(deck_head,text='Refresh status',command=self.refresh_dashboard).grid(row=0,column=1,rowspan=2,sticky='e')

        cards=ttk.Frame(dashboard); cards.pack(fill='x',pady=(0,10)); self.dashboard_cards_host=cards; self.dashboard_card_frames=[]; self.dashboard_card_values=[]
        for c in range(4): cards.columnconfigure(c,weight=1)
        card_specs=[('ACTIVE PILOT',self.dashboard_pilot),('SHIP & RANGE',self.dashboard_ship),('FUEL MARKET',self.dashboard_fuel),('DATA FEEDS',self.dashboard_data)]
        for c,(label,var) in enumerate(card_specs):
            f=ttk.Frame(cards,style='Card.TFrame',padding=(12,10)); f.grid(row=0,column=c,sticky='nsew',padx=(0 if c==0 else 4,0 if c==3 else 4))
            self.dashboard_card_frames.append(f)
            ttk.Label(f,text=label,style='CardTitle.TLabel').pack(anchor='w')
            cv=ttk.Label(f,textvariable=var,style='CardValue.TLabel',wraplength=235); cv.pack(anchor='w',pady=(4,0)); self.dashboard_card_values.append(cv)
            if c==3: ttk.Label(f,textvariable=self.dashboard_market,style='CardTitle.TLabel',wraplength=235).pack(anchor='w',pady=(5,0))

        quick=ttk.LabelFrame(dashboard,text='Quick navigation',padding=10); quick.pack(fill='x',pady=(0,10)); quick.columnconfigure((0,1),weight=1); self.dashboard_quick=quick
        self.quick_from_label=ttk.Label(quick,text='From'); self.quick_from_label.grid(row=0,column=0,sticky='w')
        self.quick_to_label=ttk.Label(quick,text='Destination'); self.quick_to_label.grid(row=0,column=1,sticky='w')
        q1=AutoCompleteEntry(quick,textvariable=self.quick_from); q1.grid(row=1,column=0,sticky='ew',padx=(0,6)); self.quick_from_entry=q1
        q2=AutoCompleteEntry(quick,textvariable=self.quick_to); q2.grid(row=1,column=1,sticky='ew',padx=(6,0)); self.quick_to_entry=q2
        self.bind_system_entry_context(q1,self.quick_from); self.bind_system_entry_context(q2,self.quick_to)
        qa=ttk.Frame(quick); qa.grid(row=2,column=0,columnspan=2,sticky='w',pady=(8,0)); self.dashboard_quick_actions=qa
        ttk.Button(qa,text='Plan route',command=self.dashboard_plan_route,style='Accent.TButton').pack(side='left')
        ttk.Button(qa,text='Set destination in EVE',command=self.dashboard_send_destination).pack(side='left',padx=6)
        ttk.Button(qa,text='Swap',command=self.dashboard_swap_quick).pack(side='left')

        deck_body=ttk.Frame(dashboard); deck_body.pack(fill='both',expand=True); deck_body.columnconfigure((0,1),weight=1); deck_body.rowconfigure(0,weight=1); self.dashboard_deck_body=deck_body
        fav=ttk.LabelFrame(deck_body,text='Pinned systems',padding=8); self.dashboard_fav=fav; fav.grid(row=0,column=0,sticky='nsew',padx=(0,5)); fav.rowconfigure(0,weight=1); fav.columnconfigure(0,weight=1)
        self.favorite_tree=ttk.Treeview(fav,columns=('system','region','security','stations'),show='headings',height=8,selectmode='browse')
        for col,title,w in [('system','System',135),('region','Region',120),('security','Sec',55),('stations','Stations',65)]:
            self.favorite_tree.heading(col,text=title); self.favorite_tree.column(col,width=w,anchor='w' if col in ('system','region') else 'e')
        self.favorite_tree.grid(row=0,column=0,sticky='nsew')
        fsb=ttk.Scrollbar(fav,orient='vertical',command=self.favorite_tree.yview); fsb.grid(row=0,column=1,sticky='ns')
        fsh=ttk.Scrollbar(fav,orient='horizontal',command=self.favorite_tree.xview); fsh.grid(row=1,column=0,sticky='ew')
        self.favorite_tree.configure(yscrollcommand=fsb.set,xscrollcommand=fsh.set)
        self.favorite_tree.bind('<Double-1>',lambda e:self.dashboard_use_favorite())
        self.favorite_tree.bind('<Button-3>',self.dashboard_favorite_context)
        fa=ttk.Frame(fav); fa.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(7,0))
        ttk.Button(fa,text='Use as destination',command=self.dashboard_use_favorite).pack(side='left')
        ttk.Button(fa,text='Remove pin',command=self.dashboard_remove_selected_favorite).pack(side='left',padx=6)

        rec=ttk.LabelFrame(deck_body,text='Recent routes',padding=8); self.dashboard_rec=rec; rec.grid(row=0,column=1,sticky='nsew',padx=(5,0)); rec.rowconfigure(0,weight=1); rec.columnconfigure(0,weight=1)
        self.recent_route_tree=ttk.Treeview(rec,columns=('route','ship','jumps','ly'),show='headings',height=8,selectmode='browse')
        for col,title,w in [('route','Route',230),('ship','Ship',105),('jumps','Jumps',55),('ly','LY',65)]:
            self.recent_route_tree.heading(col,text=title); self.recent_route_tree.column(col,width=w,anchor='w' if col in ('route','ship') else 'e')
        self.recent_route_tree.grid(row=0,column=0,sticky='nsew')
        rs=ttk.Scrollbar(rec,orient='vertical',command=self.recent_route_tree.yview); rs.grid(row=0,column=1,sticky='ns')
        rsh=ttk.Scrollbar(rec,orient='horizontal',command=self.recent_route_tree.xview); rsh.grid(row=1,column=0,sticky='ew')
        self.recent_route_tree.configure(yscrollcommand=rs.set,xscrollcommand=rsh.set)
        self.recent_route_tree.bind('<Double-1>',lambda e:self.dashboard_load_recent())
        rca=ttk.Frame(rec); rca.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(7,0))
        ttk.Button(rca,text='Load route',command=self.dashboard_load_recent).pack(side='left')
        ttk.Button(rca,text='Clear history',command=self.dashboard_clear_recent).pack(side='left',padx=6)
        # v3 Capsuleer Command Center — live multi-character context, searchable assets,
        # contracts, industry, skill queue and actionable alerts in one cockpit surface.
        cmd_head=ttk.Frame(command); cmd_head.pack(fill='x',pady=(0,10)); cmd_head.columnconfigure(0,weight=1)
        ttk.Label(cmd_head,text='CAPSULEER COMMAND CENTER',style='SectionTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(cmd_head,text='Live ESI telemetry across connected characters • assets • contracts • industry • skill queue',style='SectionSub.TLabel').grid(row=1,column=0,sticky='w')
        cmd_actions=ttk.Frame(cmd_head); cmd_actions.grid(row=0,column=1,rowspan=2,sticky='e')
        ttk.Button(cmd_actions,text='SYNC SELECTED',command=lambda:self.sync_command_center(False),style='Accent.TButton').pack(side='left')
        ttk.Button(cmd_actions,text='SYNC ALL',command=lambda:self.sync_command_center(True),style='Ghost.TButton').pack(side='left',padx=(6,0))

        cmd_cards=ttk.Frame(command); cmd_cards.pack(fill='x',pady=(0,10)); self.command_cards_host=cmd_cards; self.command_card_frames=[]; self.command_card_values=[]
        for c in range(4):cmd_cards.columnconfigure(c,weight=1)
        for c,(title,var) in enumerate((('CURRENT LOCATION',self.command_metric_location),('ACTIVE SHIP',self.command_metric_ship),('WALLET',self.command_metric_wallet),('ONLINE STATE',self.command_metric_online))):
            box=ttk.Frame(cmd_cards,style='Card.TFrame',padding=(12,10)); box.grid(row=0,column=c,sticky='nsew',padx=(0 if c==0 else 4,0 if c==3 else 4)); self.command_card_frames.append(box)
            ttk.Label(box,text=title,style='CardTitle.TLabel').pack(anchor='w'); cv=ttk.Label(box,textvariable=var,style='CardValue.TLabel',wraplength=240); cv.pack(anchor='w',pady=(4,0)); self.command_card_values.append(cv)

        cmd_book=ttk.Notebook(command); cmd_book.pack(fill='both',expand=True)
        cmd_live=ttk.Frame(cmd_book,padding=8); cmd_assets=ttk.Frame(cmd_book,padding=8); cmd_contracts=ttk.Frame(cmd_book,padding=8); cmd_work=ttk.Frame(cmd_book,padding=8); cmd_alerts=ttk.Frame(cmd_book,padding=8)
        for pg,title in ((cmd_live,'LIVE PILOTS'),(cmd_assets,'ASSET FINDER'),(cmd_contracts,'CONTRACTS'),(cmd_work,'INDUSTRY & SKILLS'),(cmd_alerts,'ALERTS')):cmd_book.add(pg,text=title)

        cmd_live.rowconfigure(0,weight=1); cmd_live.columnconfigure(0,weight=1)
        self.command_char_tree=ttk.Treeview(cmd_live,columns=('pilot','system','region','ship','clones','online','wallet','sync'),show='headings',selectmode='browse')
        for col,title,w,anchor in [('pilot','Pilot',135,'w'),('system','System',115,'w'),('region','Region',105,'w'),('ship','Ship',140,'w'),('clones','Jump clones',70,'center'),('online','Online',70,'center'),('wallet','Wallet ISK',105,'e'),('sync','Synced',120,'w')]:
            self.command_char_tree.heading(col,text=title); self.command_char_tree.column(col,width=w,anchor=anchor)
        self.command_char_tree.grid(row=0,column=0,sticky='nsew'); clsb=ttk.Scrollbar(cmd_live,orient='vertical',command=self.command_char_tree.yview); clsb.grid(row=0,column=1,sticky='ns'); clsh=ttk.Scrollbar(cmd_live,orient='horizontal',command=self.command_char_tree.xview); clsh.grid(row=1,column=0,sticky='ew'); self.command_char_tree.configure(yscrollcommand=clsb.set,xscrollcommand=clsh.set)
        self.command_char_tree.bind('<<TreeviewSelect>>',lambda e:self.command_selected_changed())
        self.command_char_tree.bind('<Double-1>',lambda e:self.command_use_selected_character())
        cmd_livebar=ttk.Frame(cmd_live); cmd_livebar.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(8,0))
        ttk.Button(cmd_livebar,text='Use selected pilot',command=self.command_use_selected_character).pack(side='left')
        ttk.Button(cmd_livebar,text='Set current location as route origin',command=self.command_location_to_route).pack(side='left',padx=6)
        ttk.Label(cmd_livebar,textvariable=self.command_status,style='HUD.TLabel').pack(side='left',padx=(12,0))

        cmd_assets.columnconfigure(0,weight=1); cmd_assets.rowconfigure(1,weight=2); cmd_assets.rowconfigure(4,weight=3)
        af=ttk.Frame(cmd_assets); af.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,8)); af.columnconfigure(0,weight=1)
        ttk.Entry(af,textvariable=self.asset_search_var).grid(row=0,column=0,sticky='ew')
        ttk.Button(af,text='SEARCH ASSETS',command=self.refresh_asset_search,style='Accent.TButton').grid(row=0,column=1,padx=(8,0))
        ttk.Button(af,text='REFRESH ESTIMATES',command=lambda:self.refresh_asset_market_prices(force=True),style='Ghost.TButton').grid(row=0,column=2,padx=(6,0))
        ttk.Button(af,text='OPEN MARKET IN EVE',command=self.open_selected_asset_market).grid(row=0,column=3,padx=(6,0))
        ttk.Checkbutton(af,text='Exclude fitted ship modules',variable=self.asset_exclude_fitted_var,command=self.refresh_asset_search).grid(row=0,column=4,padx=(10,0),sticky='e')

        asset_system_box=ttk.Frame(cmd_assets); asset_system_box.grid(row=1,column=0,columnspan=2,sticky='nsew'); asset_system_box.columnconfigure(0,weight=1); asset_system_box.rowconfigure(0,weight=1)
        self.asset_system_tree=ttk.Treeview(asset_system_box,columns=('system','region','pilots','stacks','units','value'),show='headings',selectmode='browse',height=9)
        for col,title,w,anchor in [('system','System',165,'w'),('region','Region',145,'w'),('pilots','Pilots',70,'center'),('stacks','Stacks',80,'e'),('units','Units',95,'e'),('value','Estimated ISK',150,'e')]:
            self.asset_system_tree.heading(col,text=title); self.asset_system_tree.column(col,width=w,anchor=anchor,stretch=(col in ('system','region')))
        self.asset_system_tree.grid(row=0,column=0,sticky='nsew')
        assb=ttk.Scrollbar(asset_system_box,orient='vertical',command=self.asset_system_tree.yview); assb.grid(row=0,column=1,sticky='ns')
        assh=ttk.Scrollbar(asset_system_box,orient='horizontal',command=self.asset_system_tree.xview); assh.grid(row=1,column=0,sticky='ew')
        self.asset_system_tree.configure(yscrollcommand=assb.set,xscrollcommand=assh.set)
        self.asset_system_tree.bind('<<TreeviewSelect>>',lambda e:self.asset_system_selected())
        self.asset_system_tree.bind('<Button-3>',self.asset_system_context_menu,add='+')
        self.asset_system_tree.bind('<MouseWheel>',lambda e,t=self.asset_system_tree:self._asset_tree_mousewheel(t,e),add='+')
        ttk.Label(cmd_assets,textvariable=self.asset_value_status,style='HUD.TLabel').grid(row=2,column=0,columnspan=2,sticky='w',pady=(7,2))
        ttk.Label(cmd_assets,textvariable=self.asset_selected_summary,style='SectionSub.TLabel').grid(row=3,column=0,columnspan=2,sticky='w',pady=(0,6))

        asset_detail_box=ttk.Frame(cmd_assets); asset_detail_box.grid(row=4,column=0,columnspan=2,sticky='nsew'); asset_detail_box.columnconfigure(0,weight=1); asset_detail_box.rowconfigure(0,weight=1)
        self.asset_tree=ttk.Treeview(asset_detail_box,columns=('pilot','item','qty','location','flag','unit_value','value'),show='headings',selectmode='browse')
        for col,title,w,anchor in [('pilot','Pilot',115,'w'),('item','Item / Ship',225,'w'),('qty','Qty',65,'e'),('location','Location',255,'w'),('flag','Hangar / Flag',115,'w'),('unit_value','Est / unit',105,'e'),('value','Est total',120,'e')]:
            self.asset_tree.heading(col,text=title); self.asset_tree.column(col,width=w,anchor=anchor,stretch=(col in ('item','location')))
        self.asset_tree.grid(row=0,column=0,sticky='nsew')
        asb=ttk.Scrollbar(asset_detail_box,orient='vertical',command=self.asset_tree.yview); asb.grid(row=0,column=1,sticky='ns')
        ash=ttk.Scrollbar(asset_detail_box,orient='horizontal',command=self.asset_tree.xview); ash.grid(row=1,column=0,sticky='ew')
        self.asset_tree.configure(yscrollcommand=asb.set,xscrollcommand=ash.set)
        self.asset_tree.bind('<Double-1>',lambda e:self.open_selected_asset_market())
        self.asset_tree.bind('<MouseWheel>',lambda e,t=self.asset_tree:self._asset_tree_mousewheel(t,e),add='+')
        ttk.Label(cmd_assets,textvariable=self.asset_status,style='HUD.TLabel').grid(row=5,column=0,columnspan=2,sticky='w',pady=(8,0))

        cmd_contracts.columnconfigure(0,weight=1); cmd_contracts.rowconfigure(0,weight=3); cmd_contracts.rowconfigure(2,weight=2)
        contract_book=ttk.Notebook(cmd_contracts); contract_book.grid(row=0,column=0,columnspan=2,sticky='nsew')
        self.contract_trees={}
        contract_columns=('pilot','title','type','status','start','end','reward','collateral','expires')
        contract_specs=[('pilot','Pilot',110,'w'),('title','Contract',185,'w'),('type','Type',105,'w'),('status','Status',125,'w'),('start','Start location',190,'w'),('end','End location',190,'w'),('reward','Reward',95,'e'),('collateral','Collateral',95,'e'),('expires','Expires',135,'w')]
        for key,label in (('outstanding','OUTSTANDING'),('in_progress','IN PROGRESS'),('finished','FINISHED')):
            page=ttk.Frame(contract_book,padding=4); page.columnconfigure(0,weight=1); page.rowconfigure(0,weight=1); contract_book.add(page,text=label)
            tree=ttk.Treeview(page,columns=contract_columns,show='headings',selectmode='browse')
            for col,title,w,anchor in contract_specs:tree.heading(col,text=title); tree.column(col,width=w,anchor=anchor)
            tree.grid(row=0,column=0,sticky='nsew'); sb=ttk.Scrollbar(page,orient='vertical',command=tree.yview); sb.grid(row=0,column=1,sticky='ns'); sh=ttk.Scrollbar(page,orient='horizontal',command=tree.xview); sh.grid(row=1,column=0,sticky='ew'); tree.configure(yscrollcommand=sb.set,xscrollcommand=sh.set)
            tree.bind('<<TreeviewSelect>>',lambda e,t=tree:self.contract_selected_changed(t))
            tree.bind('<Double-1>',lambda e:self.open_selected_contract())
            self.contract_trees[key]=tree
        self.contract_tree=self.contract_trees['outstanding']
        cbar=ttk.Frame(cmd_contracts); cbar.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(8,6))
        ttk.Button(cbar,text='OPEN IN EVE',command=self.open_selected_contract,style='Accent.TButton').pack(side='left')
        ttk.Button(cbar,text='PLAN ROUTE',command=self.plan_selected_contract).pack(side='left',padx=6)
        ttk.Button(cbar,text='LOAD CONTRACT ITEMS',command=self.load_selected_contract_items).pack(side='left')
        ttk.Label(cbar,textvariable=self.contract_detail_var,style='HUD.TLabel').pack(side='left',padx=(12,0))
        details=ttk.LabelFrame(cmd_contracts,text='Selected contract items',padding=6); details.grid(row=2,column=0,columnspan=2,sticky='nsew'); details.columnconfigure(0,weight=1); details.rowconfigure(0,weight=1)
        self.contract_items_tree=ttk.Treeview(details,columns=('item','qty','side','singleton'),show='headings')
        for col,title,w,anchor in [('item','Item',360,'w'),('qty','Qty',90,'e'),('side','Contract side',140,'w'),('singleton','State',105,'w')]:self.contract_items_tree.heading(col,text=title); self.contract_items_tree.column(col,width=w,anchor=anchor)
        self.contract_items_tree.grid(row=0,column=0,sticky='nsew'); cis=ttk.Scrollbar(details,orient='vertical',command=self.contract_items_tree.yview); cis.grid(row=0,column=1,sticky='ns'); cih=ttk.Scrollbar(details,orient='horizontal',command=self.contract_items_tree.xview); cih.grid(row=1,column=0,sticky='ew'); self.contract_items_tree.configure(yscrollcommand=cis.set,xscrollcommand=cih.set)

        cmd_work.columnconfigure((0,1),weight=1); cmd_work.rowconfigure(0,weight=1)
        ind=ttk.LabelFrame(cmd_work,text='Industry jobs',padding=6); ind.grid(row=0,column=0,sticky='nsew',padx=(0,4)); ind.columnconfigure(0,weight=1); ind.rowconfigure(0,weight=1)
        self.industry_tree=ttk.Treeview(ind,columns=('pilot','activity','blueprint','facility','status','end'),show='headings')
        for col,title,w in [('pilot','Pilot',105),('activity','Activity',145),('blueprint','Blueprint / Product',190),('facility','Facility',210),('status','Status',90),('end','Ends',135)]:self.industry_tree.heading(col,text=title); self.industry_tree.column(col,width=w,anchor='w')
        self.industry_tree.grid(row=0,column=0,sticky='nsew'); ih=ttk.Scrollbar(ind,orient='horizontal',command=self.industry_tree.xview); ih.grid(row=1,column=0,sticky='ew'); self.industry_tree.configure(xscrollcommand=ih.set)
        sq=ttk.LabelFrame(cmd_work,text='Skill queue',padding=6); sq.grid(row=0,column=1,sticky='nsew',padx=(4,0)); sq.columnconfigure(0,weight=1); sq.rowconfigure(0,weight=1)
        self.skillqueue_tree=ttk.Treeview(sq,columns=('pilot','skill','level','finish'),show='headings')
        for col,title,w in [('pilot','Pilot',110),('skill','Skill',220),('level','Level',55),('finish','Finishes',145)]:self.skillqueue_tree.heading(col,text=title); self.skillqueue_tree.column(col,width=w,anchor='w' if col!='level' else 'center')
        self.skillqueue_tree.grid(row=0,column=0,sticky='nsew'); sqh=ttk.Scrollbar(sq,orient='horizontal',command=self.skillqueue_tree.xview); sqh.grid(row=1,column=0,sticky='ew'); self.skillqueue_tree.configure(xscrollcommand=sqh.set)

        cmd_alerts.columnconfigure(0,weight=1); cmd_alerts.rowconfigure(0,weight=1)
        self.alert_tree=ttk.Treeview(cmd_alerts,columns=('level','pilot','alert','when'),show='headings')
        for col,title,w in [('level','Level',80),('pilot','Pilot / Op',130),('alert','Alert',560),('when','When',150)]:self.alert_tree.heading(col,text=title); self.alert_tree.column(col,width=w,anchor='w')
        self.alert_tree.grid(row=0,column=0,sticky='nsew'); alsb=ttk.Scrollbar(cmd_alerts,orient='vertical',command=self.alert_tree.yview); alsb.grid(row=0,column=1,sticky='ns'); alsh=ttk.Scrollbar(cmd_alerts,orient='horizontal',command=self.alert_tree.xview); alsh.grid(row=1,column=0,sticky='ew'); self.alert_tree.configure(yscrollcommand=alsb.set,xscrollcommand=alsh.set)

        # Skill Queue Planner — local planning/editor surface. ESI exposes the queue
        # for reading but does not provide a write endpoint, so this produces a legal
        # dependency-aware plan for the player to reproduce in the EVE client.
        sp_head=ttk.Frame(skillplanner); sp_head.pack(fill='x',pady=(0,10)); sp_head.columnconfigure(0,weight=1)
        ttk.Label(sp_head,text='SKILL QUEUE PLANNER',style='SectionTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(sp_head,text='Shortest training items first — while keeping every CCP skill prerequisite in legal order.',style='SectionSub.TLabel').grid(row=1,column=0,sticky='w')
        sp_actions=ttk.Frame(sp_head); sp_actions.grid(row=0,column=1,rowspan=2,sticky='e')
        ttk.Button(sp_actions,text='IMPORT CURRENT QUEUE',command=self.skillplan_import,style='Ghost.TButton').pack(side='left')
        ttk.Button(sp_actions,text='OPTIMISE SHORTEST-FIRST',command=self.skillplan_optimise,style='Accent.TButton').pack(side='left',padx=(6,0))
        ttk.Button(sp_actions,text='RESET',command=self.skillplan_reset).pack(side='left',padx=(6,0))

        sp_top=ttk.Frame(skillplanner,style='Panel.TFrame',padding=(12,10)); sp_top.pack(fill='x',pady=(0,10)); sp_top.columnconfigure(1,weight=1)
        ttk.Label(sp_top,text='PILOT',style='PanelHUD.TLabel').grid(row=0,column=0,sticky='w')
        self.skillplan_character_combo=ttk.Combobox(sp_top,textvariable=self.skillplan_character,state='readonly',width=28)
        self.skillplan_character_combo.grid(row=1,column=0,sticky='w',padx=(0,12))
        ttk.Label(sp_top,textvariable=self.skillplan_summary,style='HUD.TLabel').grid(row=1,column=1,sticky='w')
        ttk.Label(sp_top,text='Planner only: CCP ESI has no skill-queue write endpoint, so changes are not pushed into the game automatically.',style='PanelHUD.TLabel').grid(row=2,column=0,columnspan=2,sticky='w',pady=(8,0))

        sp_body=ttk.Frame(skillplanner); sp_body.pack(fill='both',expand=True); sp_body.columnconfigure(0,weight=1); sp_body.rowconfigure(0,weight=1)
        self.skillplan_tree=ttk.Treeview(sp_body,columns=('order','skill','level','time','prereq','status'),show='headings',selectmode='browse')
        for col,title,w,anchor in [('order','#',45,'e'),('skill','Skill',260,'w'),('level','Level',65,'center'),('time','Training time',115,'e'),('prereq','Prerequisites',390,'w'),('status','Status',145,'w')]:
            self.skillplan_tree.heading(col,text=title); self.skillplan_tree.column(col,width=w,anchor=anchor)
        self.skillplan_tree.grid(row=0,column=0,sticky='nsew'); spsb=ttk.Scrollbar(sp_body,orient='vertical',command=self.skillplan_tree.yview); spsb.grid(row=0,column=1,sticky='ns'); spsh=ttk.Scrollbar(sp_body,orient='horizontal',command=self.skillplan_tree.xview); spsh.grid(row=1,column=0,sticky='ew'); self.skillplan_tree.configure(yscrollcommand=spsb.set,xscrollcommand=spsh.set)
        sp_bar=ttk.Frame(skillplanner); sp_bar.pack(fill='x',pady=(8,0))
        ttk.Button(sp_bar,text='MOVE UP',command=lambda:self.skillplan_move(-1)).pack(side='left')
        ttk.Button(sp_bar,text='MOVE DOWN',command=lambda:self.skillplan_move(1)).pack(side='left',padx=(6,0))
        ttk.Button(sp_bar,text='COPY FOR EVE',command=self.skillplan_copy).pack(side='left',padx=(12,0))
        ttk.Button(sp_bar,text='OPEN CHARACTERS',command=lambda:self.tabs.select(self.character_tab)).pack(side='left',padx=(6,0))
        ttk.Label(sp_bar,textvariable=self.skillplan_status,style='HUD.TLabel').pack(side='left',padx=(14,0))

        # Hunting / Roam Intelligence — stargate-local target discovery using public
        # CCP last-hour activity plus sovereignty context. Exact local population and
        # ESS bank values are intentionally not guessed because ESI does not expose them.
        hunt_head=ttk.Frame(hunting); hunt_head.pack(fill='x',pady=(0,10)); hunt_head.columnconfigure(0,weight=1)
        ttk.Label(hunt_head,text='HUNTING // ROAM INTELLIGENCE',style='SectionTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(hunt_head,text='Find nearby ratting, PvP and likely ESS targets by normal stargate hops from an origin system.',style='SectionSub.TLabel').grid(row=1,column=0,sticky='w')
        ha=ttk.Frame(hunt_head); ha.grid(row=0,column=1,rowspan=2,sticky='e')
        ttk.Button(ha,text='REFRESH CCP INTEL',command=lambda:self.refresh_hunting_intel(True),style='Ghost.TButton').pack(side='left')
        ttk.Button(ha,text='SCAN AREA',command=self.scan_hunting_area,style='Accent.TButton').pack(side='left',padx=(6,0))

        filters=ttk.Frame(hunting,style='Panel.TFrame',padding=(12,10)); filters.pack(fill='x',pady=(0,10))
        for c in range(5):filters.columnconfigure(c,weight=1)
        ttk.Label(filters,text='ORIGIN SYSTEM',style='PanelHUD.TLabel').grid(row=0,column=0,sticky='w')
        hunt_entry=AutoCompleteEntry(filters,textvariable=self.hunt_origin); hunt_entry.grid(row=1,column=0,sticky='ew',padx=(0,8)); self.bind_system_entry_context(hunt_entry,self.hunt_origin)
        ttk.Label(filters,text='MAX GATE HOPS',style='PanelHUD.TLabel').grid(row=0,column=1,sticky='w')
        ttk.Spinbox(filters,from_=1,to=30,textvariable=self.hunt_max_hops,width=8).grid(row=1,column=1,sticky='ew',padx=(0,8))
        ttk.Label(filters,text='SPACE FILTER',style='PanelHUD.TLabel').grid(row=0,column=2,sticky='w')
        ttk.Combobox(filters,textvariable=self.hunt_security,values=['All k-space','Low + Null','Null only'],state='readonly').grid(row=1,column=2,sticky='ew',padx=(0,8))
        ttk.Label(filters,text='HUNT PROFILE',style='PanelHUD.TLabel').grid(row=0,column=3,sticky='w')
        ttk.Combobox(filters,textvariable=self.hunt_mode,values=['Ratter Hunt','PvP Activity','ESS Hunt','Balanced Roam'],state='readonly').grid(row=1,column=3,sticky='ew',padx=(0,8))
        ttk.Label(filters,text='MIN NPC KILLS / HOUR',style='PanelHUD.TLabel').grid(row=0,column=4,sticky='w')
        ttk.Spinbox(filters,from_=0,to=100000,textvariable=self.hunt_min_npc,width=10).grid(row=1,column=4,sticky='ew')

        hcards=ttk.Frame(hunting); hcards.pack(fill='x',pady=(0,10))
        for c in range(4):hcards.columnconfigure(c,weight=1)
        for c,(title,var) in enumerate((('SYSTEMS SCANNED',self.hunt_metric_systems),('RATTING HOTSPOT',self.hunt_metric_ratting),('PVP HOTSPOT',self.hunt_metric_pvp),('ESS TARGET',self.hunt_metric_ess))):
            card=ttk.Frame(hcards,style='Card.TFrame',padding=(12,10)); card.grid(row=0,column=c,sticky='nsew',padx=(0 if c==0 else 4,0 if c==3 else 4))
            ttk.Label(card,text=title,style='CardTitle.TLabel').pack(anchor='w'); ttk.Label(card,textvariable=var,style='CardValue.TLabel',wraplength=250).pack(anchor='w',pady=(4,0))

        hbody=ttk.Frame(hunting); hbody.pack(fill='both',expand=True); hbody.columnconfigure(0,weight=1); hbody.rowconfigure(0,weight=1)
        self.hunt_tree=ttk.Treeview(hbody,columns=('rank','system','region','hops','sec','traffic','npc','ships','pods','score','ess','sov'),show='headings',selectmode='browse')
        for col,title,w,anchor in [('rank','#',42,'e'),('system','System',120,'w'),('region','Region',110,'w'),('hops','Hops',55,'e'),('sec','Sec',58,'e'),('traffic','Jumps/h',70,'e'),('npc','NPC kills/h',82,'e'),('ships','Ship kills/h',82,'e'),('pods','Pod kills/h',78,'e'),('score','Hunt score',78,'e'),('ess','ESS / observed',125,'w'),('sov','Sov',58,'center')]:
            self.hunt_tree.heading(col,text=title); self.hunt_tree.column(col,width=w,anchor=anchor)
        self.hunt_tree.grid(row=0,column=0,sticky='nsew'); hsb=ttk.Scrollbar(hbody,orient='vertical',command=self.hunt_tree.yview); hsb.grid(row=0,column=1,sticky='ns'); hsh=ttk.Scrollbar(hbody,orient='horizontal',command=self.hunt_tree.xview); hsh.grid(row=1,column=0,sticky='ew'); self.hunt_tree.configure(yscrollcommand=hsb.set,xscrollcommand=hsh.set)
        self.hunt_tree.tag_configure('hot',background='#173522'); self.hunt_tree.tag_configure('danger',background='#351a1f'); self.hunt_tree.tag_configure('ess',background='#2a2815')
        self.hunt_tree.bind('<Double-1>',lambda e:self.hunt_set_selected_destination())
        self.hunt_tree.bind('<Button-3>',self.hunt_tree_context_menu)
        hbar=ttk.Frame(hunting); hbar.pack(fill='x',pady=(8,0))
        ttk.Button(hbar,text='SET DESTINATION IN EVE',command=self.hunt_set_selected_destination,style='Accent.TButton').pack(side='left')
        ttk.Button(hbar,text='USE SELECTED AS NEW ORIGIN',command=self.hunt_use_selected_origin).pack(side='left',padx=6)
        ttk.Button(hbar,text='RECORD OBSERVED ESS BANK',command=self.hunt_record_selected_ess).pack(side='left')
        ttk.Button(hbar,text='CLEAR OBSERVED ESS',command=self.hunt_clear_selected_ess).pack(side='left',padx=6)
        ttk.Label(hunting,textvariable=self.hunt_status,style='HUD.TLabel',wraplength=1060).pack(anchor='w',pady=(7,0))
        ttk.Label(hunting,text='DATA NOTE  //  CCP ESI exposes last-hour jumps plus NPC/ship/pod kills, but not an exact pilots-in-space count or live ESS Main/Reserve Bank balances. ESS observations shown here are values you record from the in-game ESS UI; unobserved ESS targets are ranked as potential only.',style='SectionSub.TLabel',wraplength=1080).pack(anchor='w',pady=(4,0))

        # Capital Operations: saved multi-ship move plans, cyno-chain execution,
        # aggregated fuel logistics, activity intelligence and route comparison.
        op_head=ttk.Frame(operations); op_head.pack(fill='x',pady=(0,10)); op_head.columnconfigure(0,weight=1)
        ttk.Label(op_head,text='CAPITAL OPERATIONS',style='SectionTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(op_head,text='Turn a route into an executable move plan • pilots • cynos • fuel • station stops • live activity',style='SectionSub.TLabel').grid(row=1,column=0,sticky='w')
        op_create=ttk.Frame(op_head); op_create.grid(row=0,column=1,rowspan=2,sticky='e')
        ttk.Entry(op_create,textvariable=self.operation_name,width=24).pack(side='left')
        ttk.Button(op_create,text='CREATE / UPDATE FROM ROUTE',command=self.create_operation_from_route,style='Accent.TButton').pack(side='left',padx=(6,0))
        ttk.Button(op_create,text='LOAD',command=self.load_operation_dialog).pack(side='left',padx=(6,0))

        nextbox=ttk.Frame(operations,style='Card.TFrame',padding=(14,11)); nextbox.pack(fill='x',pady=(0,10)); nextbox.columnconfigure(0,weight=1)
        ttk.Label(nextbox,text='OPERATION EXECUTION',style='CardTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(nextbox,textvariable=self.operation_next_summary,style='CardValue.TLabel').grid(row=1,column=0,sticky='w',pady=(3,0))
        nextacts=ttk.Frame(nextbox,style='Card.TFrame'); nextacts.grid(row=0,column=1,rowspan=2,sticky='e')
        ttk.Button(nextacts,text='SEND NEXT TO EVE',command=self.operation_send_next,style='Accent.TButton').pack(side='left')
        ttk.Button(nextacts,text='MARK LEG COMPLETE',command=self.operation_mark_complete).pack(side='left',padx=6)
        ttk.Button(nextacts,text='RESET LEGS',command=self.operation_reset_legs).pack(side='left')

        op_body=ttk.Panedwindow(operations,orient='horizontal'); op_body.pack(fill='both',expand=True)
        op_left=ttk.Frame(op_body); op_right=ttk.Frame(op_body); op_body.add(op_left,weight=3); op_body.add(op_right,weight=2)
        op_left.columnconfigure(0,weight=1); op_left.rowconfigure(1,weight=1)
        op_tools=ttk.Frame(op_left); op_tools.grid(row=0,column=0,sticky='ew',pady=(0,6))
        ttk.Button(op_tools,text='Refresh live activity',command=self.refresh_activity_intel).pack(side='left')
        ttk.Button(op_tools,text='Assign active pilot as cyno',command=self.operation_assign_active_pilot).pack(side='left',padx=6)
        ttk.Button(op_tools,text='Toggle PRIMARY / BACKUP',command=self.operation_toggle_cyno_role).pack(side='left')
        ttk.Button(op_tools,text='Add leg note',command=self.operation_edit_note).pack(side='left',padx=6)
        self.operation_route_tree=ttk.Treeview(op_left,columns=('leg','from','to','region','ly','stations','activity','status','cyno','role','note'),show='headings',selectmode='browse')
        for col,title,w,anchor in [('leg','#',40,'e'),('from','From',100,'w'),('to','To',105,'w'),('region','Region',105,'w'),('ly','LY',65,'e'),('stations','Stations',65,'e'),('activity','Activity',80,'e'),('status','Status',90,'w'),('cyno','Cyno pilot',120,'w'),('role','Role',75,'w'),('note','Note',180,'w')]:
            self.operation_route_tree.heading(col,text=title); self.operation_route_tree.column(col,width=w,anchor=anchor)
        self.operation_route_tree.grid(row=1,column=0,sticky='nsew'); opsb=ttk.Scrollbar(op_left,orient='vertical',command=self.operation_route_tree.yview); opsb.grid(row=1,column=1,sticky='ns'); opsh=ttk.Scrollbar(op_left,orient='horizontal',command=self.operation_route_tree.xview); opsh.grid(row=2,column=0,sticky='ew'); self.operation_route_tree.configure(yscrollcommand=opsb.set,xscrollcommand=opsh.set)
        self.operation_route_tree.bind('<Double-1>',lambda e:self.operation_send_selected_destination())
        ttk.Label(op_left,textvariable=self.activity_status,style='HUD.TLabel').grid(row=3,column=0,columnspan=2,sticky='w',pady=(6,0))

        op_right.columnconfigure(0,weight=1); op_right.rowconfigure(1,weight=1)
        ttk.Label(op_right,text='FLEET MANIFEST & FUEL LOGISTICS',style='HUD.TLabel').grid(row=0,column=0,sticky='w',pady=(0,5))
        self.operation_manifest_tree=ttk.Treeview(op_right,columns=('ship','qty','pilot','range','viable','isotope','fuel','cost','owned','short'),show='headings',height=8,selectmode='browse')
        for col,title,w,anchor in [('ship','Ship',115,'w'),('qty','Qty',45,'e'),('pilot','Pilot',105,'w'),('range','Range',65,'e'),('viable','Route',65,'center'),('isotope','Isotope',105,'w'),('fuel','Fuel',85,'e'),('cost','Jita ISK',90,'e'),('owned','Owned',80,'e'),('short','Short',80,'e')]:
            self.operation_manifest_tree.heading(col,text=title); self.operation_manifest_tree.column(col,width=w,anchor=anchor)
        self.operation_manifest_tree.grid(row=1,column=0,sticky='nsew'); omh=ttk.Scrollbar(op_right,orient='horizontal',command=self.operation_manifest_tree.xview); omh.grid(row=2,column=0,sticky='ew'); self.operation_manifest_tree.configure(xscrollcommand=omh.set)
        mbar=ttk.Frame(op_right); mbar.grid(row=3,column=0,sticky='ew',pady=(7,0))
        ttk.Label(mbar,text='Qty').pack(side='left'); ttk.Spinbox(mbar,from_=1,to=100,textvariable=self.operation_qty,width=5).pack(side='left',padx=(4,7))
        ttk.Button(mbar,text='Add current ship',command=self.operation_add_current_ship).pack(side='left')
        ttk.Button(mbar,text='Remove',command=self.operation_remove_manifest).pack(side='left',padx=6)
        ttk.Button(mbar,text='Assign active pilot',command=self.operation_assign_manifest_pilot).pack(side='left')
        ttk.Label(op_right,textvariable=self.operation_fuel_summary,wraplength=470,style='HUD.TLabel').grid(row=4,column=0,sticky='ew',pady=(7,0))

        compare=ttk.LabelFrame(operations,text='Route comparison matrix',padding=7); compare.pack(fill='x',pady=(10,0)); compare.columnconfigure(0,weight=1)
        ctop=ttk.Frame(compare); ctop.grid(row=0,column=0,sticky='ew',pady=(0,5)); ttk.Button(ctop,text='COMPARE ROUTES',command=self.operation_compare_routes).pack(side='left'); ttk.Button(ctop,text='Use selected comparison',command=self.operation_use_comparison).pack(side='left',padx=6); ttk.Label(ctop,textvariable=self.operation_status,style='HUD.TLabel').pack(side='left',padx=(10,0))
        self.operation_compare_tree=ttk.Treeview(compare,columns=('mode','stations','jumps','ly','stationstops','fuel','cost'),show='headings',height=4,selectmode='browse')
        for col,title,w,anchor in [('mode','Optimisation',120,'w'),('stations','Station policy',135,'w'),('jumps','Jumps',60,'e'),('ly','LY',75,'e'),('stationstops','Station stops',85,'e'),('fuel','Fuel',95,'e'),('cost','Jita cost',105,'e')]:self.operation_compare_tree.heading(col,text=title); self.operation_compare_tree.column(col,width=w,anchor=anchor)
        self.operation_compare_tree.grid(row=1,column=0,sticky='ew'); och=ttk.Scrollbar(compare,orient='horizontal',command=self.operation_compare_tree.xview); och.grid(row=2,column=0,sticky='ew'); self.operation_compare_tree.configure(xscrollcommand=och.set)

        ttk.Label(jump,text='SINGLE LEG ANALYSIS',style='SectionTitle.TLabel').pack(anchor='w')
        ttk.Label(jump,text='Validate range, cyno legality, fuel burn, Jita cost and station availability for one jump.',style='SectionSub.TLabel').pack(anchor='w',pady=(1,12))
        route=ttk.Frame(jump); route.pack(fill='x'); route.columnconfigure((0,1),weight=1)
        ttk.Label(route,text='From system').grid(row=0,column=0,sticky='w'); ttk.Label(route,text='To system').grid(row=0,column=1,sticky='w')
        self.e1=AutoCompleteEntry(route,textvariable=self.frm); self.e1.grid(row=1,column=0,sticky='ew',padx=(0,8)); self.e2=AutoCompleteEntry(route,textvariable=self.to); self.e2.grid(row=1,column=1,sticky='ew')
        self.bind_system_entry_context(self.e1,self.frm); self.bind_system_entry_context(self.e2,self.to)
        acts=ttk.Frame(jump); acts.pack(fill='x',pady=12)
        ttk.Button(acts,text='Calculate jump',command=self.calculate,style='Accent.TButton').pack(side='left'); self.update_btn=ttk.Button(acts,text='Update EVE data',command=self.do_update); self.update_btn.pack(side='left',padx=8)
        self.result=tk.Text(jump,height=14,wrap='word',font=('Consolas',11),state='disabled',bg='#081018',fg='#dce8ef',insertbackground='#dce8ef',selectbackground='#174f6b',selectforeground='#ffffff',relief='flat',bd=0,highlightthickness=1,highlightbackground='#203341',padx=14,pady=12); self.result.pack(fill='both',expand=True)
        ttk.Label(reach,text='JUMP ENVELOPE SCANNER',style='SectionTitle.TLabel').pack(anchor='w')
        ttk.Label(reach,text='Scan every geometric destination inside the selected hull range, then filter by legality, security and NPC station availability.',style='SectionSub.TLabel').pack(anchor='w',pady=(1,12))
        self.range_origin=tk.StringVar(); self.sec_filter=tk.StringVar(value='All')
        top=ttk.Frame(reach); top.pack(fill='x'); top.columnconfigure(0,weight=1)
        ttk.Label(top,text='ORIGIN SYSTEM',style='HUD.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(top,text='SECURITY',style='HUD.TLabel').grid(row=0,column=1,sticky='w',padx=(10,0))
        ttk.Label(top,text='STATION FILTER',style='HUD.TLabel').grid(row=0,column=2,sticky='w',padx=(10,0))
        self.re=AutoCompleteEntry(top,textvariable=self.range_origin); self.re.grid(row=1,column=0,sticky='ew')
        self.bind_system_entry_context(self.re,self.range_origin)
        ttk.Combobox(top,textvariable=self.sec_filter,values=['All','High-sec','Low-sec','Null-sec'],state='readonly',width=14).grid(row=1,column=1,padx=(10,0))
        ttk.Combobox(top,textvariable=self.range_station_filter,values=['All systems','NPC station systems','No NPC stations'],state='readonly',width=20).grid(row=1,column=2,padx=(10,0))
        ra=ttk.Frame(reach); ra.pack(fill='x',pady=10)
        ttk.Button(ra,text='Find systems in range',command=self.find_range,style='Accent.TButton').pack(side='left'); ttk.Button(ra,text='Use selected as origin',command=self.use_selected_origin).pack(side='left',padx=8)
        ttk.Checkbutton(ra,text='Legal destinations only',variable=self.range_legal_only,command=lambda:self.find_range() if self.range_origin.get().strip() else None).pack(side='left',padx=(8,4))
        self.range_summary=tk.StringVar(value='Enter an origin system and search.')
        ttk.Label(reach,textvariable=self.range_summary).pack(anchor='w',pady=(0,2))
        ttk.Label(reach,textvariable=self.live_rules_status).pack(anchor='w',pady=(0,6))
        table=ttk.Frame(reach); table.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(table,columns=('system','region','distance','security','stations','cyno','status','fuel','cost'),show='headings',selectmode='browse')
        for col,title,w in [('system','System',145),('region','Region',120),('distance','LY',70),('security','Sec',58),('stations','NPC stations',82),('cyno','Cyno',78),('status','Jump status',175),('fuel','Fuel',82),('cost','Fuel cost',105)]:
            self.tree.heading(col,text=title,command=lambda c=col:self.sort_tree(c)); self.tree.column(col,width=w,anchor='w' if col in ('system','region','cyno','status') else 'e')
        self.tree.tag_configure('high',foreground='#72d28b')
        self.tree.tag_configure('low',foreground='#e6b85c')
        self.tree.tag_configure('null',foreground='#ef7a72')
        self.tree.tag_configure('blocked',background='#2a1418')
        table.columnconfigure(0,weight=1); table.rowconfigure(0,weight=1); sb=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview); sh=ttk.Scrollbar(table,orient='horizontal',command=self.tree.xview); self.tree.configure(yscrollcommand=sb.set,xscrollcommand=sh.set); self.tree.grid(row=0,column=0,sticky='nsew'); sb.grid(row=0,column=1,sticky='ns'); sh.grid(row=1,column=0,sticky='ew')
        self.tree.bind('<Double-1>',lambda e:self.use_selected_origin())
        self.tree.bind('<Button-3>',self.range_tree_context_menu)

        ttk.Label(planner,text='ROUTE INTELLIGENCE',style='SectionTitle.TLabel').pack(anchor='w')
        ttk.Label(planner,text='Build station-aware capital jump chains, validate cyno rules, optimise fuel or hops, and push destinations into EVE.',style='SectionSub.TLabel').pack(anchor='w',pady=(1,12))
        self.route_from=tk.StringVar(); self.route_to=tk.StringVar(); self.route_sec=tk.StringVar(value='Low + Null')
        self.route_mode=tk.StringVar(value='Fewest Jumps')
        self.waypoint_input=tk.StringVar(); self.avoid_input=tk.StringVar(); self.avoid_regions=tk.StringVar()
        rp=ttk.Frame(planner); rp.pack(fill='x'); rp.columnconfigure((0,1),weight=1)
        ttk.Label(rp,text='Start system').grid(row=0,column=0,sticky='w'); ttk.Label(rp,text='Destination system').grid(row=0,column=1,sticky='w')
        r1=AutoCompleteEntry(rp,textvariable=self.route_from); r1.grid(row=1,column=0,sticky='ew',padx=(0,8)); r2=AutoCompleteEntry(rp,textvariable=self.route_to); r2.grid(row=1,column=1,sticky='ew')
        self.bind_system_entry_context(r1,self.route_from); self.bind_system_entry_context(r2,self.route_to)
        opts=ttk.Frame(planner); opts.pack(fill='x',pady=(10,6))
        for col in range(3): opts.columnconfigure(col,weight=1)
        ttk.Label(opts,text='SECURITY ENVELOPE',style='HUD.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(opts,text='ROUTE OBJECTIVE',style='HUD.TLabel').grid(row=0,column=1,sticky='w',padx=(10,0))
        ttk.Label(opts,text='NPC STATION POLICY',style='HUD.TLabel').grid(row=0,column=2,sticky='w',padx=(10,0))
        ttk.Combobox(opts,textvariable=self.route_sec,values=['All systems','Low + Null','Null only'],state='readonly').grid(row=1,column=0,sticky='ew')
        ttk.Combobox(opts,textvariable=self.route_mode,values=['Fewest Jumps','Shortest Distance'],state='readonly').grid(row=1,column=1,sticky='ew',padx=(10,0))
        ttk.Combobox(opts,textvariable=self.route_station_policy,values=['Any systems','Prefer NPC stations','NPC stations only','Avoid NPC stations'],state='readonly').grid(row=1,column=2,sticky='ew',padx=(10,0))

        actionbar=ttk.Frame(planner); actionbar.pack(fill='x',pady=(2,7))
        ttk.Button(actionbar,text='FIND ROUTE',command=self.find_route,style='Accent.TButton').pack(side='left')
        ttk.Button(actionbar,text='Reverse',command=self.reverse_route).pack(side='left',padx=(7,0))
        ttk.Button(actionbar,text='Send destination to EVE',command=lambda:self.set_eve_destination(self.route_to.get())).pack(side='left',padx=(7,0))
        ttk.Button(actionbar,text='Export CSV',command=self.export_route_csv).pack(side='right')
        ttk.Button(actionbar,text='Copy route',command=self.copy_route_summary).pack(side='right',padx=(0,7))

        rules=ttk.Frame(planner); rules.pack(fill='x',pady=(0,3))
        ttk.Checkbutton(rules,text='Enforce jump legality',variable=self.enforce_legality).pack(side='left')
        ttk.Checkbutton(rules,text='Final destination must be an NPC-station system',variable=self.route_require_dest_station).pack(side='left',padx=(12,4))
        ttk.Checkbutton(rules,text='Use live CCP Incursion cyno jams',variable=self.use_live_rules).pack(side='left',padx=(12,4))
        ttk.Button(rules,text='Refresh activity',command=self.refresh_activity_intel).pack(side='right')
        ttk.Button(rules,text='Refresh live rules',command=lambda:self.refresh_live_jump_restrictions(force=True)).pack(side='right',padx=(0,6))
        ttk.Label(planner,textvariable=self.live_rules_status,style='SectionSub.TLabel').pack(anchor='w',pady=(0,2))
        ttk.Label(planner,text='Station routing tracks NPC-station presence from CCP SDE. It does not imply docking access; supercarriers/titans cannot dock in NPC stations. Player-owned Upwell structures are not globally enumerable through public ESI.',style='SectionSub.TLabel',wraplength=1080).pack(anchor='w',pady=(0,7))

        controls=ttk.LabelFrame(planner,text='ROUTE CONSTRAINTS',padding=8); controls.pack(fill='x',pady=(0,8)); controls.columnconfigure((0,1),weight=1)
        left=ttk.Frame(controls); left.grid(row=0,column=0,sticky='nsew',padx=(0,8)); left.columnconfigure(0,weight=1)
        ttk.Label(left,text='Waypoints (visited in order)').grid(row=0,column=0,columnspan=3,sticky='w')
        AutoCompleteEntry(left,textvariable=self.waypoint_input).grid(row=1,column=0,sticky='ew')
        ttk.Button(left,text='Add',command=self.add_waypoint).grid(row=1,column=1,padx=4)
        ttk.Button(left,text='Remove',command=self.remove_waypoint).grid(row=1,column=2)
        self.waypoint_list=tk.Listbox(left,height=3,exportselection=False,bg='#081018',fg='#dce8ef',selectbackground='#174f6b',selectforeground='#ffffff',highlightthickness=1,highlightbackground='#203341',relief='flat',bd=0); self.waypoint_list.grid(row=2,column=0,columnspan=3,sticky='ew',pady=(4,0))

        right=ttk.Frame(controls); right.grid(row=0,column=1,sticky='nsew'); right.columnconfigure(0,weight=1)
        ttk.Label(right,text='Avoid systems').grid(row=0,column=0,columnspan=3,sticky='w')
        AutoCompleteEntry(right,textvariable=self.avoid_input).grid(row=1,column=0,sticky='ew')
        ttk.Button(right,text='Add',command=self.add_avoid_system).grid(row=1,column=1,padx=4)
        ttk.Button(right,text='Remove',command=self.remove_avoid_system).grid(row=1,column=2)
        self.avoid_list=tk.Listbox(right,height=3,exportselection=False,bg='#081018',fg='#dce8ef',selectbackground='#174f6b',selectforeground='#ffffff',highlightthickness=1,highlightbackground='#203341',relief='flat',bd=0); self.avoid_list.grid(row=2,column=0,columnspan=3,sticky='ew',pady=(4,0))
        ttk.Label(controls,text='Avoid regions (comma-separated names)').grid(row=1,column=0,sticky='w',pady=(8,0))
        ttk.Entry(controls,textvariable=self.avoid_regions).grid(row=2,column=0,columnspan=2,sticky='ew',pady=(2,0))

        self.route_summary=tk.StringVar(value='Finds a legal jump-drive route using range, cyno rules, station policy, waypoints and avoid lists.')
        ttk.Label(planner,textvariable=self.route_summary).pack(anchor='w',pady=(0,8))
        metricbar=ttk.Frame(planner); metricbar.pack(fill='x',pady=(0,8))
        metrics=[('JUMPS',self.route_metric_jumps),('TOTAL RANGE',self.route_metric_ly),('FUEL',self.route_metric_fuel),('JITA COST',self.route_metric_cost),('STATION STOPS',self.route_metric_stations)]
        for idx,(label,var) in enumerate(metrics):
            metricbar.columnconfigure(idx,weight=1)
            card=ttk.Frame(metricbar,style='Card.TFrame',padding=(10,7)); card.grid(row=0,column=idx,sticky='nsew',padx=(0 if idx==0 else 4,0 if idx==len(metrics)-1 else 4))
            ttk.Label(card,text=label,style='CardTitle.TLabel').pack(anchor='w')
            ttk.Label(card,textvariable=var,style='CardValue.TLabel').pack(anchor='w',pady=(1,0))

        self.route_view_tabs=ttk.Notebook(planner); self.route_view_tabs.pack(fill='both',expand=True)
        rt=ttk.Frame(self.route_view_tabs,padding=(0,4,0,0))
        map_view=ttk.Frame(self.route_view_tabs,padding=(6,6,6,4))
        self.route_view_tabs.add(rt,text='Route legs')
        self.route_view_tabs.add(map_view,text='Route map')

        self.route_tree=ttk.Treeview(rt,columns=('leg','from','to','region','distance','security','stations','cyno','status','activity','fuel','cost'),show='headings')
        for col,title,w in [('leg','Leg',38),('from','From',100),('to','To',100),('region','Region',105),('distance','LY',55),('security','Sec',52),('stations','Stations',68),('cyno','Cyno',70),('status','Legality',130),('activity','Activity',65),('fuel','Fuel',78),('cost','Cost',95)]:
            self.route_tree.heading(col,text=title); self.route_tree.column(col,width=w,anchor='w' if col in ('from','to','region','cyno','status') else 'e')
        self.route_tree.tag_configure('high',foreground='#72d28b')
        self.route_tree.tag_configure('low',foreground='#e6b85c')
        self.route_tree.tag_configure('null',foreground='#ef7a72')
        self.route_tree.tag_configure('blocked',background='#2a1418')
        rt.columnconfigure(0,weight=1); rt.rowconfigure(0,weight=1); rsb=ttk.Scrollbar(rt,orient='vertical',command=self.route_tree.yview); rsh=ttk.Scrollbar(rt,orient='horizontal',command=self.route_tree.xview); self.route_tree.configure(yscrollcommand=rsb.set,xscrollcommand=rsh.set); self.route_tree.grid(row=0,column=0,sticky='nsew'); rsb.grid(row=0,column=1,sticky='ns'); rsh.grid(row=1,column=0,sticky='ew')
        self.route_tree.bind('<Button-3>',self.route_tree_context_menu)

        map_tools=ttk.Frame(map_view); map_tools.pack(fill='x',pady=(0,6))
        ttk.Button(map_tools,text='Fit route',command=self.route_map_fit).pack(side='left')
        ttk.Button(map_tools,text='Zoom +',command=lambda:self.route_map_zoom_by(1.25)).pack(side='left',padx=(6,2))
        ttk.Button(map_tools,text='Zoom −',command=lambda:self.route_map_zoom_by(0.8)).pack(side='left',padx=2)
        ttk.Checkbutton(map_tools,text='System labels',variable=self.route_map_show_labels,command=self.redraw_route_map).pack(side='left',padx=(12,4))
        ttk.Checkbutton(map_tools,text='Region labels',variable=self.route_map_show_regions,command=self.redraw_route_map).pack(side='left',padx=4)
        ttk.Checkbutton(map_tools,text='Station rings',variable=self.route_map_show_stations,command=self.redraw_route_map).pack(side='left',padx=4)
        ttk.Checkbutton(map_tools,text='Jump radius',variable=self.route_map_show_radius,command=self.redraw_route_map).pack(side='left',padx=4)
        ttk.Button(map_tools,text='Use selected as range origin',command=self.route_map_use_selected_origin).pack(side='right')
        ttk.Button(map_tools,text='Send chain to EVE',command=self.send_route_to_eve,style='Accent.TButton').pack(side='right',padx=(0,8))
        ttk.Label(map_view,text='TACTICAL PROJECTION  •  ▣ NPC station system  •  green high-sec  •  amber low-sec  •  red null-sec  •  leg labels use true CCP SDE 3D light-year distance',style='SectionSub.TLabel',wraplength=1040).pack(anchor='w',pady=(0,5))
        self.route_map_canvas=tk.Canvas(map_view,background='#0b1118',highlightthickness=1,highlightbackground='#33404d',height=300,cursor='crosshair')
        self.route_map_canvas.pack(fill='both',expand=True)
        self.route_map_canvas.bind('<Configure>',self._schedule_route_map_redraw)
        self.route_map_canvas.bind('<Button-1>',self.route_map_click)
        self.route_map_canvas.bind('<Double-1>',lambda e:self.route_map_use_selected_origin())
        self.route_map_canvas.bind('<Button-3>',self.route_map_context_menu)
        self.route_map_canvas.bind('<MouseWheel>',self.route_map_mousewheel)
        ttk.Label(map_view,textvariable=self.route_map_status).pack(anchor='w',pady=(6,0))

        # EVE SSO multi-character skill integration. The release build embeds the
        # public PKCE client ID, so end users only see normal EVE login controls.
        ttk.Label(character,text='EVE Characters & Jump Skills',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(character,text='Add one or more EVE characters through CCP Single Sign-On. Select a character to use its real jump skills throughout the planner. No EVE password or client secret is stored by this application.',wraplength=920).pack(anchor='w',pady=(0,12))
        if not APP_SSO_CLIENT_ID:
            ttk.Label(character,text='This development build does not have an EVE SSO Client ID embedded. Build the release with developer_settings.local.json before distributing it.',wraplength=900).pack(anchor='w',pady=(0,10))

        chars_box=ttk.LabelFrame(character,text='Connected characters',padding=12); chars_box.pack(fill='both',expand=True)
        char_table=ttk.Frame(chars_box); char_table.pack(fill='both',expand=True)
        self.esi_character_tree=ttk.Treeview(char_table,columns=('active','character','jdc','jfc','jf','ingame','companion','synced'),show='headings',height=8,selectmode='browse')
        for col,title,width in [('active','Using',55),('character','Character',190),('jdc','JDC',55),('jfc','JFC',55),('jf','Jump Freighters',105),('ingame','In-game route',105),('companion','Command data',105),('synced','Last synced',155)]:
            self.esi_character_tree.heading(col,text=title)
            self.esi_character_tree.column(col,width=width,anchor='w' if col in ('character','synced') else 'center')
        char_table.columnconfigure(0,weight=1); char_table.rowconfigure(0,weight=1); csb=ttk.Scrollbar(char_table,orient='vertical',command=self.esi_character_tree.yview); csh=ttk.Scrollbar(char_table,orient='horizontal',command=self.esi_character_tree.xview); self.esi_character_tree.configure(yscrollcommand=csb.set,xscrollcommand=csh.set)
        self.esi_character_tree.grid(row=0,column=0,sticky='nsew'); csb.grid(row=0,column=1,sticky='ns'); csh.grid(row=1,column=0,sticky='ew')
        self.esi_character_tree.bind('<<TreeviewSelect>>',lambda e:self._character_selection_changed())
        self.esi_character_tree.bind('<Double-1>',lambda e:self.use_selected_character())

        ca=ttk.Frame(chars_box); ca.pack(fill='x',pady=(10,0))
        self.esi_connect_btn=ttk.Button(ca,text='Add character / re-authorize',command=self.connect_eve_character,style='Accent.TButton'); self.esi_connect_btn.pack(side='left')
        self.esi_refresh_btn=ttk.Button(ca,text='Refresh selected',command=self.refresh_character_skills,state='disabled'); self.esi_refresh_btn.pack(side='left',padx=(8,0))
        self.esi_refresh_all_btn=ttk.Button(ca,text='Refresh all',command=self.refresh_all_character_skills,state='disabled'); self.esi_refresh_all_btn.pack(side='left',padx=(8,0))
        self.esi_use_btn=ttk.Button(ca,text='Use selected',command=self.use_selected_character,state='disabled'); self.esi_use_btn.pack(side='left',padx=(8,0))
        self.esi_remove_btn=ttk.Button(ca,text='Remove selected',command=self.remove_eve_character,state='disabled'); self.esi_remove_btn.pack(side='left',padx=(8,0))
        ttk.Checkbutton(chars_box,text='Automatically apply skills when I choose or add a character',variable=self.esi_auto_apply).pack(anchor='w',pady=(10,0))
        ttk.Label(chars_box,textvariable=self.esi_character_status,wraplength=880).pack(anchor='w',pady=(8,0))

        sk=ttk.LabelFrame(character,text='Selected character skills',padding=12); sk.pack(fill='x',pady=(12,0)); sk.columnconfigure(1,weight=1)
        ttk.Label(sk,text='Character').grid(row=0,column=0,sticky='w',pady=3)
        ttk.Label(sk,textvariable=self.esi_character_name,font=('Segoe UI',10,'bold')).grid(row=0,column=1,sticky='w',padx=(12,0),pady=3)
        for rr,name in enumerate(CHARACTER_SKILLS,1):
            ttk.Label(sk,text=name).grid(row=rr,column=0,sticky='w',pady=3)
            ttk.Label(sk,textvariable=self.esi_skill_vars[name],width=8,anchor='w',font=('Segoe UI',10,'bold')).grid(row=rr,column=1,sticky='w',padx=(12,0),pady=3)
        ttk.Label(sk,textvariable=self.esi_skills_status,wraplength=880).grid(row=len(CHARACTER_SKILLS)+1,column=0,columnspan=2,sticky='w',pady=(10,0))

        privacy=ttk.LabelFrame(character,text='Sign-in & privacy',padding=12); privacy.pack(fill='x',pady=(12,0))
        ttk.Label(privacy,text='The distributed app uses a public PKCE Client ID and no client secret. v3 can optionally read character skills, location, current ship, online state, assets, contracts, industry jobs, wallet, skill queue, clones and accessible player-structure names, and can use EVE UI waypoint/window actions. CCP shows the complete permission list during authorization. Refresh tokens are stored separately per character and protected with Windows DPAPI for the current Windows user.',wraplength=900).pack(anchor='w')

        # Live Jita isotope pricing comes from CCP's public ESI market-order endpoint.
        ttk.Label(prices,text='Jita Fuel Prices',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(prices,text='Automatically pulled from CCP ESI for Jita IV - Moon 4 - Caldari Navy Assembly Plant. Fuel-cost calculations use the lowest current sell order at Jita 4-4.',wraplength=920).pack(anchor='w',pady=(0,12))
        pg=ttk.LabelFrame(prices,text='Jita 4-4 isotope order book (ISK per unit)',padding=12); pg.pack(fill='x')
        pg.columnconfigure(1,weight=1); pg.columnconfigure(2,weight=1)
        ttk.Label(pg,text='Isotope',font=('Segoe UI',9,'bold')).grid(row=0,column=0,sticky='w',pady=(0,5))
        ttk.Label(pg,text='Best sell — used',font=('Segoe UI',9,'bold')).grid(row=0,column=1,sticky='w',padx=(8,12),pady=(0,5))
        ttk.Label(pg,text='Best buy',font=('Segoe UI',9,'bold')).grid(row=0,column=2,sticky='w',padx=(8,12),pady=(0,5))
        ttk.Label(pg,text='Race',font=('Segoe UI',9,'bold')).grid(row=0,column=3,sticky='w',pady=(0,5))
        isotope_rows=[('Helium Isotopes','Amarr'),('Hydrogen Isotopes','Minmatar'),('Nitrogen Isotopes','Caldari'),('Oxygen Isotopes','Gallente / ORE')]
        for r,(iso,faction) in enumerate(isotope_rows,1):
            ttk.Label(pg,text=iso,width=20).grid(row=r,column=0,sticky='w',pady=4)
            ttk.Entry(pg,textvariable=self.fuel_price_vars[iso],width=18,state='readonly').grid(row=r,column=1,sticky='ew',padx=(8,12),pady=4)
            ttk.Entry(pg,textvariable=self.market_buy_vars[iso],width=18,state='readonly').grid(row=r,column=2,sticky='ew',padx=(8,12),pady=4)
            ttk.Label(pg,text=faction).grid(row=r,column=3,sticky='w',pady=4)
        pa=ttk.Frame(prices); pa.pack(fill='x',pady=(10,0))
        self.price_refresh_btn=ttk.Button(pa,text='Refresh Jita prices now',command=lambda:self.refresh_jita_prices(force=True)); self.price_refresh_btn.pack(side='left')
        ttk.Label(pa,text='CCP market orders are cached for 5 minutes; the app will not auto-poll faster than that.').pack(side='left',padx=12)
        ttk.Label(prices,textvariable=self.price_status,wraplength=920).pack(anchor='w',pady=(12,0))
        note=ttk.LabelFrame(prices,text='How costs are calculated',padding=12); note.pack(fill='x',pady=(16,0))
        ttk.Label(note,text='Fuel cost = rounded isotope units required × current Jita 4-4 best sell price. The app refreshes on startup when the cached CCP price is older than 5 minutes. If ESI is temporarily unavailable, the last successful Jita price remains in use.',wraplength=920).pack(anchor='w')

        # Saved profiles/routes live in ~/.eve_jump_planner/config.json so application updates do not erase them.
        ttk.Label(saved,text='Saved Profiles & Routes',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(saved,text='Save your usual ship skills and complete route setups. These are kept separately from the application files.').pack(anchor='w',pady=(0,12))
        savegrid=ttk.Frame(saved); savegrid.pack(fill='both',expand=True); savegrid.columnconfigure((0,1),weight=1); savegrid.rowconfigure(1,weight=1)

        prof=ttk.LabelFrame(savegrid,text='Ship & skill profiles',padding=10); prof.grid(row=0,column=0,rowspan=2,sticky='nsew',padx=(0,6)); prof.columnconfigure(0,weight=1); prof.rowconfigure(2,weight=1)
        ttk.Label(prof,text='Profile name').grid(row=0,column=0,sticky='w')
        ttk.Entry(prof,textvariable=self.profile_name).grid(row=1,column=0,sticky='ew',pady=(2,6))
        self.profile_list=tk.Listbox(prof,height=10,exportselection=False,bg='#081018',fg='#dce8ef',selectbackground='#174f6b',selectforeground='#ffffff',highlightthickness=1,highlightbackground='#203341',relief='flat',bd=0); self.profile_list.grid(row=2,column=0,sticky='nsew')
        self.profile_list.bind('<Double-1>',lambda e:self.load_profile())
        pb=ttk.Frame(prof); pb.grid(row=3,column=0,sticky='ew',pady=(8,0))
        ttk.Button(pb,text='Save current',command=self.save_profile).pack(side='left')
        ttk.Button(pb,text='Load',command=self.load_profile).pack(side='left',padx=6)
        ttk.Button(pb,text='Delete',command=self.delete_profile).pack(side='left')

        routes=ttk.LabelFrame(savegrid,text='Saved routes',padding=10); routes.grid(row=0,column=1,rowspan=2,sticky='nsew',padx=(6,0)); routes.columnconfigure(0,weight=1); routes.rowconfigure(2,weight=1)
        ttk.Label(routes,text='Route name').grid(row=0,column=0,sticky='w')
        ttk.Entry(routes,textvariable=self.saved_route_name).grid(row=1,column=0,sticky='ew',pady=(2,6))
        self.saved_route_list=tk.Listbox(routes,height=10,exportselection=False,bg='#081018',fg='#dce8ef',selectbackground='#174f6b',selectforeground='#ffffff',highlightthickness=1,highlightbackground='#203341',relief='flat',bd=0); self.saved_route_list.grid(row=2,column=0,sticky='nsew')
        self.saved_route_list.bind('<Double-1>',lambda e:self.load_saved_route())
        rb=ttk.Frame(routes); rb.grid(row=3,column=0,sticky='ew',pady=(8,0))
        ttk.Button(rb,text='Save current route',command=self.save_current_route).pack(side='left')
        ttk.Button(rb,text='Load',command=self.load_saved_route).pack(side='left',padx=6)
        ttk.Button(rb,text='Delete',command=self.delete_saved_route).pack(side='left')
        self.saved_info=tk.StringVar(value=f'Saved data file: {CONFIG}')
        ttk.Label(saved,textvariable=self.saved_info,wraplength=900).pack(anchor='w',pady=(10,0))
        self.refresh_saved_lists()

        # Update Center supports local .ejpupdate files and an optional HTTPS release feed.
        ttk.Label(updates,text='Application Update Center',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(updates,text='Use a signed-by-hash .ejpupdate package locally, or configure an HTTPS update feed so the app can check and download new releases itself. Every downloaded package is checked against the feed SHA-256 and then its internal manifest SHA-256 values before installation. User data remains outside the install folder.',wraplength=920).pack(anchor='w',pady=(0,14))

        online=ttk.LabelFrame(updates,text='Online update feed',padding=12); online.pack(fill='x'); online.columnconfigure(0,weight=1)
        ttk.Label(online,text='Feed URL (for GitHub Releases: https://github.com/jamesronaldthorn-cpu/New-Eden-Command/releases/latest/download/latest.json)').grid(row=0,column=0,columnspan=4,sticky='w')
        ttk.Entry(online,textvariable=self.update_feed_url).grid(row=1,column=0,sticky='ew',pady=(6,0))
        ttk.Button(online,text='Save',command=self.save_update_feed).grid(row=1,column=1,padx=(8,4),pady=(6,0))
        self.online_check_btn=ttk.Button(online,text='Check online',command=lambda:self.check_online_update(manual=True)); self.online_check_btn.grid(row=1,column=2,padx=4,pady=(6,0))
        self.online_download_btn=ttk.Button(online,text='Download & install',command=self.download_online_update,state='disabled'); self.online_download_btn.grid(row=1,column=3,padx=(4,0),pady=(6,0))
        ttk.Progressbar(online,variable=self.app_update_progress,maximum=100).grid(row=2,column=0,columnspan=3,sticky='ew',pady=(10,0))
        ttk.Label(online,textvariable=self.app_update_percent,width=12,anchor='e').grid(row=2,column=3,sticky='e',pady=(10,0))
        ttk.Label(online,textvariable=self.app_update_status,wraplength=860).grid(row=3,column=0,columnspan=4,sticky='w',pady=(8,0))

        uc=ttk.LabelFrame(updates,text='Install local update file',padding=12); uc.pack(fill='x',pady=(14,0)); uc.columnconfigure(0,weight=1)
        ttk.Label(uc,text=f'Current version: v{VERSION}').grid(row=0,column=0,sticky='w',columnspan=3)
        ttk.Entry(uc,textvariable=self.update_package_path,state='readonly').grid(row=1,column=0,sticky='ew',pady=(10,0))
        ttk.Button(uc,text='Choose update file…',command=self.choose_update_package).grid(row=1,column=1,padx=8,pady=(10,0))
        ttk.Button(uc,text='Install & restart',command=self.install_selected_update).grid(row=1,column=2,pady=(10,0))
        meta=ttk.LabelFrame(updates,text='What is preserved',padding=12); meta.pack(fill='x',pady=(14,0))
        ttk.Label(meta,text='✓ CCP SDE database   ✓ saved ship profiles   ✓ saved routes   ✓ Jita fuel price cache   ✓ app settings',wraplength=900).pack(anchor='w')
        ttk.Label(meta,text=f'Automatic backup folder: {BACKUPS}',wraplength=900).pack(anchor='w',pady=(6,0))
        ttk.Label(updates,text='Release builds create the Windows installer, .ejpupdate file, SHA256SUMS.txt and latest.json together. Host those files together over HTTPS and set the feed URL once; future app updates can then be handled from this screen.',wraplength=920).pack(anchor='w',pady=(14,0))

        update_box=ttk.Frame(root)
        update_box.pack(fill='x',pady=(8,0))
        update_box.columnconfigure(0,weight=1)
        ttk.Label(update_box,textvariable=self.update_detail,anchor='w').grid(row=0,column=0,sticky='ew')
        ttk.Label(update_box,textvariable=self.update_percent,width=5,anchor='e').grid(row=0,column=1,sticky='e',padx=(8,0))
        self.update_bar=ttk.Progressbar(update_box,variable=self.update_progress,maximum=100,mode='determinate')
        self.update_bar.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(3,0))
        ttk.Separator(root,orient='horizontal').pack(fill='x',pady=(10,6))
        ttk.Label(root,textvariable=self.status,anchor='w',style='Subtitle.TLabel').pack(fill='x')
    def _layout_hud_groups(self,available_width=None):
        """Reflow the global ship/skill HUD instead of letting it clip."""
        if not hasattr(self,'hud_groups') or not self.hud_groups:return
        width=int(available_width or 0)
        cols=5 if width>=1000 else (3 if width>=700 else 2)
        for g in self.hud_groups:
            try:g.grid_forget()
            except Exception:pass
        for c in range(5):
            try:self.hud_fields.columnconfigure(c,weight=0,minsize=0,uniform='')
            except Exception:pass
        for c in range(cols):self.hud_fields.columnconfigure(c,weight=1,uniform='hud')
        for i,g in enumerate(self.hud_groups):
            r=i//cols; c=i%cols
            g.grid(row=r,column=c,sticky='ew',padx=(0 if c==0 else 5,0 if c==cols-1 else 5),pady=(0 if r==0 else 7,0))

    def _on_window_configure(self,event=None):
        if event is not None and event.widget is not self:return
        old=getattr(self,'_responsive_after',None)
        if old:
            try:self.after_cancel(old)
            except Exception:pass
        self._responsive_after=self.after(70,self._apply_responsive_layout)

    def _reflow_cards(self,host,frames,value_labels,width):
        if not host or not frames:return
        cols=4 if width>=1040 else (2 if width>=660 else 1)
        for f in frames:f.grid_forget()
        for c in range(4):host.columnconfigure(c,weight=0,minsize=0,uniform='')
        for c in range(cols):host.columnconfigure(c,weight=1,uniform=str(host))
        for i,f in enumerate(frames):
            r=i//cols; c=i%cols
            f.grid(row=r,column=c,sticky='nsew',padx=(0 if c==0 else 4,0 if c==cols-1 else 4),pady=(0 if r==0 else 4,0))
        wrap=max(210,int(width/max(cols,1))-42)
        for label in value_labels:
            try:label.configure(wraplength=wrap)
            except Exception:pass

    def _apply_responsive_layout(self):
        self._responsive_after=None
        if not self.winfo_exists():return
        total=max(1,self.winfo_width())
        main=max(1,self.main_shell.winfo_width()) if hasattr(self,'main_shell') else total
        # Collapse only when the window genuinely cannot spare the measured rail
        # width.  At normal laptop/desktop widths the full names must remain visible.
        collapse_limit=max(940,int(getattr(self,'sidebar_expanded_width',258))+720)
        collapsed=total<collapse_limit
        if collapsed!=getattr(self,'sidebar_collapsed',None):
            self.sidebar_collapsed=collapsed
            try:self.sidebar.configure(width=70 if collapsed else getattr(self,'sidebar_expanded_width',258))
            except Exception:pass
            for key,button in getattr(self,'nav_buttons',{}).items():
                glyph,label=self.nav_button_meta.get(key,('•',''))
                active=(key==str(self.tabs.nametowidget(self.tabs.select()))) if self.tabs.select() else False
                if collapsed:
                    button.configure(text=glyph,style='NavCompactActive.TButton' if active else 'NavCompact.TButton')
                else:
                    button.configure(text=f'{glyph}   {label}',style='NavActive.TButton' if active else 'Nav.TButton')
            try:
                if collapsed:
                    self.brand_name_label.grid_remove(); self.brand_sub_label.grid_remove()
                    self.brand_frame.configure(padding=(14,14,10,12))
                    if self.brand_logo_compact:self.brand_logo_label.configure(image=self.brand_logo_compact)
                    self.brand_logo_label.grid_configure(row=0,column=0,rowspan=1,padx=(0,0),sticky='n')
                    self.sidebar_live_label.configure(text='LIVE'); self.sidebar_live_label.pack_configure(anchor='center',padx=0)
                    self.sidebar_build_label.configure(text=f'v{VERSION}'); self.sidebar_build_label.pack_configure(anchor='center',padx=0)
                else:
                    self.brand_name_label.grid(); self.brand_sub_label.grid()
                    self.brand_frame.configure(padding=(14,16,10,14))
                    if self.brand_logo_full:self.brand_logo_label.configure(image=self.brand_logo_full)
                    self.brand_logo_label.grid_configure(row=0,column=0,rowspan=2,padx=(0,10),sticky='w')
                    self.sidebar_live_label.configure(text='NEW EDEN AWAITS'); self.sidebar_live_label.pack_configure(anchor='w',padx=16)
                    self.sidebar_build_label.configure(text=f'v{VERSION}  •  ONLINE'); self.sidebar_build_label.pack_configure(anchor='w',padx=16)
            except Exception:pass
        # The top HUD reflows independently of the page content.
        self._layout_hud_groups(main)
        try:
            self.hero_subtitle.configure(wraplength=max(260,main-310))
            self.root_shell.configure(padding=((10 if main<760 else 18),(8 if main<760 else 12),(10 if main<760 else 18),10))
        except Exception:pass
        # Flight Deck / Command Center metric cards follow the same responsive grid.
        try:self._reflow_cards(self.dashboard_cards_host,self.dashboard_card_frames,self.dashboard_card_values,main-40)
        except Exception:pass
        try:self._reflow_cards(self.command_cards_host,self.command_card_frames,self.command_card_values,main-40)
        except Exception:pass
        # Stack Flight Deck quick-navigation fields and tables when the page is narrow.
        try:
            pw=max(1,self.dashboard_tab.canvas.winfo_width())
            q=self.dashboard_quick
            if pw<650:
                q.columnconfigure(0,weight=1); q.columnconfigure(1,weight=0)
                self.quick_from_label.grid(row=0,column=0,sticky='w')
                self.quick_from_entry.grid(row=1,column=0,sticky='ew',padx=0)
                self.quick_to_label.grid(row=2,column=0,sticky='w',pady=(7,0))
                self.quick_to_entry.grid(row=3,column=0,sticky='ew',padx=0)
                self.dashboard_quick_actions.grid(row=4,column=0,columnspan=1,sticky='w',pady=(8,0))
            else:
                q.columnconfigure((0,1),weight=1)
                self.quick_from_label.grid(row=0,column=0,sticky='w',pady=0)
                self.quick_to_label.grid(row=0,column=1,sticky='w',pady=0)
                self.quick_from_entry.grid(row=1,column=0,sticky='ew',padx=(0,6))
                self.quick_to_entry.grid(row=1,column=1,sticky='ew',padx=(6,0))
                self.dashboard_quick_actions.grid(row=2,column=0,columnspan=2,sticky='w',pady=(8,0))
            if pw<900:
                self.dashboard_deck_body.columnconfigure(0,weight=1); self.dashboard_deck_body.columnconfigure(1,weight=0)
                self.dashboard_deck_body.rowconfigure((0,1),weight=1)
                self.dashboard_fav.grid(row=0,column=0,sticky='nsew',padx=0,pady=(0,5))
                self.dashboard_rec.grid(row=1,column=0,sticky='nsew',padx=0,pady=(5,0))
            else:
                self.dashboard_deck_body.columnconfigure((0,1),weight=1); self.dashboard_deck_body.rowconfigure(0,weight=1); self.dashboard_deck_body.rowconfigure(1,weight=0)
                self.dashboard_fav.grid(row=0,column=0,sticky='nsew',padx=(0,5),pady=0)
                self.dashboard_rec.grid(row=0,column=1,sticky='nsew',padx=(5,0),pady=0)
            self.dashboard_tab._schedule_sync()
            self.command_tab._schedule_sync()
        except Exception:pass

    def _on_global_mousewheel(self,event):
        """Scroll the selected page when the pointer is not over its own scroller."""
        try:
            widget=event.widget
            klass=widget.winfo_class()
            # Let controls with their own vertical data handling keep the wheel.
            if klass in ('Treeview','Text','Listbox','TCombobox','Spinbox'):return
            page=self.page_scrolls.get(str(self.tabs.nametowidget(self.tabs.select())))
            if not page:return
            delta=-1 if event.delta>0 else 1
            if event.state & 0x0001: page.scroll_x(delta*3)
            else: page.scroll_y(delta*3)
        except Exception:
            return

    def _on_tab_changed(self,event=None):
        try:
            current=str(self.tabs.nametowidget(self.tabs.select()))
        except Exception:
            current=''
        compact=bool(getattr(self,'sidebar_collapsed',False))
        for key,button in getattr(self,'nav_buttons',{}).items():
            try:
                glyph,label=self.nav_button_meta.get(key,('•',''))
                active=(key==current)
                if compact: button.configure(text=glyph,style='NavCompactActive.TButton' if active else 'NavCompact.TButton')
                else: button.configure(text=f'{glyph}   {label}',style='NavActive.TButton' if active else 'Nav.TButton')
            except Exception: pass
        self.refresh_dashboard()
        try:
            if hasattr(self,'command_tab') and current==str(self.command_tab): self.refresh_command_center_views()
            if hasattr(self,'operations_tab') and current==str(self.operations_tab): self.refresh_operation_ui()
        except Exception: pass

    def write(self,text):
        self.result.config(state='normal'); self.result.delete('1.0','end'); self.result.insert('1.0',text); self.result.config(state='disabled')
    def show_update_dialog(self):
        # Use a dedicated modal progress window so an EVE data update is always visible.
        if self.update_window is not None:
            try:
                if self.update_window.winfo_exists():
                    self.update_window.deiconify(); self.update_window.lift(); return
            except tk.TclError:
                pass
        win=tk.Toplevel(self)
        self.update_window=win
        win.title('Updating EVE Data')
        win.transient(self)
        win.resizable(False,False)
        win.protocol('WM_DELETE_WINDOW', lambda: None if self.update_running else self.close_update_dialog())
        frame=ttk.Frame(win,padding=20); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='EVE Data Update',font=('Segoe UI',15,'bold')).pack(anchor='w')
        ttk.Label(frame,text='Downloading and preparing the CCP Static Data Export.').pack(anchor='w',pady=(2,14))
        row=ttk.Frame(frame); row.pack(fill='x')
        self.update_dialog_detail=tk.StringVar(value=self.update_detail.get())
        self.update_dialog_percent=tk.StringVar(value=self.update_percent.get())
        ttk.Label(row,textvariable=self.update_dialog_detail,anchor='w',width=58).pack(side='left',fill='x',expand=True)
        ttk.Label(row,textvariable=self.update_dialog_percent,width=6,anchor='e').pack(side='right',padx=(12,0))
        self.update_dialog_progress=tk.DoubleVar(value=self.update_progress.get())
        bar=ttk.Progressbar(frame,variable=self.update_dialog_progress,maximum=100,mode='determinate',length=520)
        bar.pack(fill='x',pady=(8,14))
        self.update_dialog_close=ttk.Button(frame,text='Close',command=self.close_update_dialog,state='disabled')
        self.update_dialog_close.pack(anchor='e')
        win.update_idletasks()
        # Centre over the main application window.
        w=max(win.winfo_reqwidth(),560); h=win.winfo_reqheight()
        x=self.winfo_rootx()+max(0,(self.winfo_width()-w)//2)
        y=self.winfo_rooty()+max(0,(self.winfo_height()-h)//2)
        win.geometry(f'{w}x{h}+{x}+{y}')
        win.lift(); win.focus_force(); win.grab_set()

    def close_update_dialog(self):
        win=self.update_window
        if win is None: return
        try:
            if win.grab_current() is win: win.grab_release()
            win.destroy()
        except tk.TclError:
            pass
        self.update_window=None
        self.update_dialog_detail=None
        self.update_dialog_percent=None
        self.update_dialog_progress=None
        self.update_dialog_close=None

    def set_update_progress(self,message,percent=None):
        self.update_detail.set(message)
        if self.update_dialog_detail is not None:
            self.update_dialog_detail.set(message)
        if percent is None:
            # Keep the current percentage when the server does not expose a download size.
            return
        pct=max(0.0,min(100.0,float(percent)))
        self.update_progress.set(pct)
        self.update_percent.set(f'{int(round(pct))}%')
        if self.update_dialog_progress is not None:
            self.update_dialog_progress.set(pct)
        if self.update_dialog_percent is not None:
            self.update_dialog_percent.set(f'{int(round(pct))}%')

    def finish_update_dialog(self,message,success=True):
        self.update_running=False
        self.set_update_progress(message,100 if success else self.update_progress.get())
        if self.update_window is not None:
            try:
                self.update_window.title('EVE Data Update Complete' if success else 'EVE Data Update Failed')
                self.update_window.protocol('WM_DELETE_WINDOW', self.close_update_dialog)
                if self.update_dialog_close is not None:
                    self.update_dialog_close.config(state='normal')
                self.update_window.lift()
            except tk.TclError:
                pass

    def refresh_dashboard(self):
        """Refresh the Flight Deck without making network calls."""
        try:
            chars=self._sso_characters()
            rec=chars.get(str(int(self.esi_character_id or 0)),{}) if self.esi_character_id else {}
            pilot=str(rec.get('character_name') or 'No EVE character selected')
            skills=rec.get('skills',{}) if isinstance(rec.get('skills',{}),dict) else {}
            if rec:
                pilot+=f"\nJDC {skills.get('Jump Drive Calibration','—')} • JFC {skills.get('Jump Fuel Conservation','—')} • JF {skills.get('Jump Freighters','—')}"
            self.dashboard_pilot.set(pilot)
            sh=SHIPS.get(self.ship.get(),{})
            maxr=float(sh.get('range',0))*(1+0.2*int(self.jdc.get()))
            self.dashboard_ship.set(f"{self.ship.get()}\n{sh.get('class','')} • max {maxr:.2f} LY")
            iso=str(sh.get('isotope','—')); price=self.fuel_price(iso)
            fuel_line=iso
            if price is not None: fuel_line+=f"\nJita sell {price:,.2f} ISK/unit"
            else: fuel_line+='\nJita sell unavailable'
            self.dashboard_fuel.set(fuel_line)
            meta=load_meta(); build=meta.get('sde_build','not installed'); count=int(meta.get('system_count',0) or 0)
            self.dashboard_data.set(f"CCP SDE {build}\n{count:,} systems • {int(meta.get('npc_station_count',0) or 0):,} NPC stations")
            age=self._market_cache_age()
            self.dashboard_market.set('Jita fuel: '+('not refreshed yet' if age is None else (f'{age}s old' if age<120 else f'{age//60} min old')))
        except Exception:
            pass
        if self.favorite_tree is not None:
            self.favorite_tree.delete(*self.favorite_tree.get_children())
            valid=[]
            for name in list(self.favorite_systems):
                row=system(name)
                if not row: continue
                valid.append(row[1])
                band=security_band(row[5]).replace('-sec','').lower()
                iid=self.favorite_tree.insert('', 'end', values=(row[1],row[7],f'{float(row[5]):.3f}',(str(int(row[8])) if len(row)>8 and int(row[8] or 0)>0 else '—')),tags=(band,))
            self.favorite_systems=valid
            self.favorite_tree.tag_configure('high',foreground='#72d28b')
            self.favorite_tree.tag_configure('low',foreground='#e6b85c')
            self.favorite_tree.tag_configure('null',foreground='#ef7a72')
        if self.recent_route_tree is not None:
            self.recent_route_tree.delete(*self.recent_route_tree.get_children())
            for idx,item in enumerate(self.recent_routes[:20]):
                route=f"{item.get('start','?')} → {item.get('destination','?')}"
                try:ly=float(item.get('ly',0) or 0)
                except Exception:ly=0.0
                self.recent_route_tree.insert('', 'end', iid=str(idx), values=(route,item.get('ship',''),item.get('jumps',''),f'{ly:.2f}'))

    def dashboard_swap_quick(self):
        a,b=self.quick_from.get(),self.quick_to.get(); self.quick_from.set(b); self.quick_to.set(a)

    def dashboard_plan_route(self):
        a=system(self.quick_from.get()); b=system(self.quick_to.get())
        if not a or not b:
            messagebox.showwarning('Quick navigation','Choose valid start and destination systems from the dropdown.',parent=self); return
        self.route_from.set(a[1]); self.route_to.set(b[1]); self.tabs.select(self.planner_tab); self.find_route()

    def dashboard_send_destination(self):
        row=system(self.quick_to.get())
        if not row:
            messagebox.showwarning('Quick navigation','Choose a valid destination system first.',parent=self); return
        self.set_eve_destination(row[1])

    def dashboard_use_favorite(self):
        if self.favorite_tree is None:return
        sel=self.favorite_tree.selection()
        if not sel:return
        vals=self.favorite_tree.item(sel[0],'values')
        if vals:self.quick_to.set(str(vals[0]))

    def dashboard_remove_selected_favorite(self):
        if self.favorite_tree is None:return
        sel=self.favorite_tree.selection()
        if not sel:return
        vals=self.favorite_tree.item(sel[0],'values')
        if vals:self.toggle_favorite_system(str(vals[0]),force_remove=True)

    def dashboard_favorite_context(self,event):
        if self.favorite_tree is None:return
        iid=self.favorite_tree.identify_row(event.y)
        if not iid:return
        self.favorite_tree.selection_set(iid)
        vals=self.favorite_tree.item(iid,'values')
        if vals:self.show_system_context_menu(event,str(vals[0]))

    def toggle_favorite_system(self,name,force_remove=False):
        row=system(name)
        if not row:return
        canonical=str(row[1]); folded=canonical.casefold()
        existing=next((x for x in self.favorite_systems if x.casefold()==folded),None)
        if existing:
            self.favorite_systems=[x for x in self.favorite_systems if x.casefold()!=folded]
        elif not force_remove:
            self.favorite_systems.insert(0,canonical); self.favorite_systems=self.favorite_systems[:40]
        self.config['favorite_systems']=list(self.favorite_systems)
        try:save_config(self.config)
        except Exception:pass
        self.refresh_dashboard()

    def record_recent_route(self,start,destination,jumps,total_ly,total_cost=None):
        item={'start':str(start),'destination':str(destination),'ship':self.ship.get(),'jumps':int(jumps),'ly':round(float(total_ly),4),'security':self.route_sec.get(),'mode':self.route_mode.get(),'station_policy':self.route_station_policy.get(),'require_dest_station':bool(self.route_require_dest_station.get()),'timestamp_utc':datetime.now(timezone.utc).isoformat()}
        if total_cost is not None:item['cost']=round(float(total_cost),2)
        key=(item['start'].casefold(),item['destination'].casefold(),item['ship'].casefold())
        cleaned=[]
        for old in self.recent_routes:
            oldkey=(str(old.get('start','')).casefold(),str(old.get('destination','')).casefold(),str(old.get('ship','')).casefold())
            if oldkey!=key:cleaned.append(old)
        self.recent_routes=[item]+cleaned
        self.recent_routes=self.recent_routes[:20]
        self.config['recent_routes']=list(self.recent_routes)
        try:save_config(self.config)
        except Exception:pass

    def dashboard_load_recent(self):
        if self.recent_route_tree is None:return
        sel=self.recent_route_tree.selection()
        if not sel:return
        try:item=self.recent_routes[int(sel[0])]
        except Exception:return
        start=str(item.get('start','')); dest=str(item.get('destination','')); ship=normalize_ship_name(item.get('ship',self.ship.get()),self.ship.get())
        self.ship.set(ship); self.update_ship_controls(); self.route_from.set(start); self.route_to.set(dest); self.quick_from.set(start); self.quick_to.set(dest)
        if item.get('security') in ('All systems','Low + Null','Null only'): self.route_sec.set(item['security'])
        if item.get('mode') in ('Fewest Jumps','Shortest Distance'): self.route_mode.set(item['mode'])
        if item.get('station_policy') in ('Any systems','Prefer NPC stations','NPC stations only','Avoid NPC stations'): self.route_station_policy.set(item['station_policy'])
        self.route_require_dest_station.set(bool(item.get('require_dest_station',False)))
        self.tabs.select(self.planner_tab); self.find_route()

    def dashboard_clear_recent(self):
        if not self.recent_routes:return
        if not messagebox.askyesno('Recent routes','Clear the recent route history?',parent=self):return
        self.recent_routes=[]; self.config['recent_routes']=[]
        try:save_config(self.config)
        except Exception:pass
        self.refresh_dashboard()

    # -------------------- v3 Capsuleer Command Center --------------------
    def _companion_cache(self):
        cache=self.config.setdefault('companion_cache',{})
        if not isinstance(cache,dict): cache={}; self.config['companion_cache']=cache
        return cache

    def _snapshot_for(self,cid):
        return self._companion_cache().get(str(int(cid)),{}) if cid else {}

    def _name_cache(self):
        cache=self.config.setdefault('esi_name_cache',{})
        if not isinstance(cache,dict):cache={}; self.config['esi_name_cache']=cache
        return cache

    def _snapshot_name(self,snap,entity_id,kind='entity'):
        try:eid=int(entity_id or 0)
        except Exception:return '—'
        if not eid:return '—'
        local=location_label(eid) if kind=='location' else None
        if local and local not in ('Unresolved location',):return local
        names=(snap or {}).get('resolved_names',{}) if isinstance(snap,dict) else {}
        rec=names.get(str(eid),{}) if isinstance(names,dict) else {}
        if isinstance(rec,dict) and rec.get('name'):return str(rec.get('name'))
        cached=self._name_cache().get(str(eid),{})
        if isinstance(cached,dict) and cached.get('name'):return str(cached.get('name'))
        if kind=='location' and eid>=1_000_000_000_000:return 'Restricted / unresolved structure'
        return 'Unresolved location' if kind=='location' else 'Unknown entity'

    def _resolved_location_system(self,snap,location_id):
        direct=location_to_system(location_id)
        if direct:return direct
        try:lid=int(location_id or 0)
        except Exception:return None
        names=(snap or {}).get('resolved_names',{}) if isinstance(snap,dict) else {}
        rec=names.get(str(lid),{}) if isinstance(names,dict) else {}
        if not rec:
            cached=self._name_cache().get(str(lid),{})
            rec=cached if isinstance(cached,dict) else {}
        try:sid=int(rec.get('system_id') or 0)
        except Exception:sid=0
        return system_by_id(sid) if sid else None

    def _resolve_snapshot_names(self,cid,snap,access,scopes):
        """Resolve IDs in a character snapshot to player-facing EVE names.

        Static item/skill names come from the SDE. Universe names cover owners,
        systems and NPC stations. Player structures are resolved with the
        authenticated structure endpoint when the token has that permission.
        Raw IDs remain internal and are not used as display labels.
        """
        ids=set(); location_ids=set()
        for c in snap.get('contracts') or []:
            for key in ('issuer_id','issuer_corporation_id','assignee_id','acceptor_id','start_location_id','end_location_id'):
                try:
                    val=int(c.get(key) or 0)
                    if val:ids.add(val)
                    if key.endswith('location_id') and val:location_ids.add(val)
                except Exception:pass
        clones=snap.get('clones') or {}
        if isinstance(clones,dict):
            locs=[]
            if isinstance(clones.get('home_location'),dict):locs.append(clones['home_location'])
            locs.extend(clones.get('jump_clones') or [])
            for row in locs:
                try:val=int((row or {}).get('location_id') or 0)
                except Exception:val=0
                if val:ids.add(val); location_ids.add(val)
        for j in snap.get('industry_jobs') or []:
            for key in ('facility_id','station_id'):
                try:val=int(j.get(key) or 0)
                except Exception:val=0
                if val:ids.add(val); location_ids.add(val)
        assets=snap.get('assets') or []
        asset_by_item={int(a.get('item_id')):a for a in assets if isinstance(a,dict) and a.get('item_id')}
        for a in assets:
            if not isinstance(a,dict):continue
            if str(a.get('location_type') or '').lower() in ('station','solar_system','other'):
                try:val=int(a.get('location_id') or 0)
                except Exception:val=0
                if val:ids.add(val); location_ids.add(val)
            # Also collect every root location.  Some asset trees only expose the
            # station/structure after walking one or more parent item IDs.
            try:root=self._asset_root_location(snap,a,asset_by_item)
            except Exception:root=0
            if root:ids.add(root); location_ids.add(root)
        # Repair/prime static type-name cache for everything this snapshot can display.
        type_ids=set()
        ship=snap.get('ship') or {}
        if isinstance(ship,dict):
            try:type_ids.add(int(ship.get('ship_type_id') or 0))
            except Exception:pass
        for a in snap.get('assets') or []:
            try:type_ids.add(int(a.get('type_id') or 0))
            except Exception:pass
        for j in snap.get('industry_jobs') or []:
            for key in ('blueprint_type_id','product_type_id'):
                try:type_ids.add(int(j.get(key) or 0))
                except Exception:pass
        for q in snap.get('skillqueue') or []:
            try:type_ids.add(int(q.get('skill_id') or 0))
            except Exception:pass
        skills_payload=snap.get('skills_full') or {}
        for row in skills_payload.get('skills',[]) if isinstance(skills_payload,dict) else []:
            try:type_ids.add(int(row.get('skill_id') or 0))
            except Exception:pass
        try:ensure_type_names(type_ids)
        except Exception:pass

        resolved={}
        cache=self._name_cache()
        unresolved=[]
        for eid in ids:
            cached=cache.get(str(eid))
            if isinstance(cached,dict) and cached.get('name'):resolved[str(eid)]=dict(cached)
            else:unresolved.append(eid)
        if unresolved:
            try:
                bulk=resolve_universe_names(unresolved)
                for eid,rec in bulk.items():
                    if rec.get('name'):
                        resolved[str(eid)]=rec; cache[str(eid)]=rec
            except Exception:
                pass
        # /universe/names intentionally does not resolve Upwell structures.
        # Resolve accessible structures individually and cache the result.
        if ESI_STRUCTURES_SCOPE in set(scopes or []):
            remaining=[eid for eid in location_ids if eid>=1_000_000_000_000 and not int((resolved.get(str(eid),{}) or {}).get('system_id') or 0)]
            for eid in remaining[:120]:
                rec=resolve_structure_info(eid,access)
                if rec and rec.get('name'):
                    resolved[str(eid)]=rec; cache[str(eid)]=rec

        # The local SDE station index is normally sufficient, but legacy/new
        # station rows can occasionally be absent from a user's current local DB.
        # Enrich only root locations that still have no system mapping using the
        # public station endpoint, then cache the station -> solar-system mapping.
        station_candidates=[]
        for eid in location_ids:
            if eid<=0 or eid>=1_000_000_000_000:continue
            if location_to_system(eid):continue
            rec=resolved.get(str(eid),{}) if isinstance(resolved.get(str(eid),{}),dict) else {}
            if int(rec.get('system_id') or 0):continue
            station_candidates.append(eid)
        for eid in station_candidates[:160]:
            rec=resolve_station_info(eid)
            if rec:
                previous=resolved.get(str(eid),{}) if isinstance(resolved.get(str(eid),{}),dict) else {}
                merged=dict(previous); merged.update(rec)
                resolved[str(eid)]=merged; cache[str(eid)]=merged
        snap['resolved_names']=resolved
        return snap

    def _asset_location_label(self,snap,asset):
        assets=snap.get('assets') or [] if isinstance(snap,dict) else []
        by_item={int(a.get('item_id')):a for a in assets if isinstance(a,dict) and a.get('item_id')}
        seen=set()
        def walk(a,depth=0):
            if not isinstance(a,dict) or depth>8:return 'Unresolved location'
            try:lid=int(a.get('location_id') or 0)
            except Exception:return 'Unresolved location'
            ltype=str(a.get('location_type') or '').lower()
            if ltype=='item' and lid in by_item and lid not in seen:
                seen.add(lid); parent=by_item[lid]
                container=type_name(parent.get('type_id'))
                base=walk(parent,depth+1)
                return f'{container} • {base}' if base and base!='Unresolved location' else container
            return self._snapshot_name(snap,lid,'location')
        return walk(asset)

    def _iso_short(self,value):
        if not value:return '—'
        try:
            dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime('%Y-%m-%d %H:%M')
        except Exception:return str(value)[:16]

    def sync_command_center(self,all_characters=False):
        if self.companion_sync_running:return
        chars=self._sso_characters()
        if not chars:
            messagebox.showinfo('Command Center','Add an EVE character first.',parent=self); self.tabs.select(self.character_tab); return
        ids=[]
        if all_characters:
            for key in chars:
                try:ids.append(int(key))
                except Exception:pass
        else:
            cid=self._selected_character_id() or int(self.esi_character_id or 0)
            if cid:ids=[cid]
        if not ids:return
        self.companion_sync_running=True; self.command_status.set(f'Syncing {len(ids)} character(s) from CCP ESI…')
        def work():
            results=[]; errors=[]
            for idx,cid in enumerate(ids,1):
                try:
                    access,rec=self._access_token_for_character(cid)
                    scopes=rec.get('scopes',[])
                    snap=fetch_character_companion_snapshot(cid,access,scopes)
                    snap=self._resolve_snapshot_names(cid,snap,access,scopes)
                    results.append((cid,snap)); self.after(0,lambda i=idx,n=len(ids):self.command_status.set(f'Syncing live ESI data + resolving names… {i}/{n}'))
                except Exception as e:errors.append((cid,str(e)))
            self.after(0,lambda:self._finish_command_sync(results,errors))
        threading.Thread(target=work,daemon=True).start()

    def _finish_command_sync(self,results,errors):
        cache=self._companion_cache()
        for cid,snap in results:cache[str(cid)]=snap
        save_config(self.config); self.companion_sync_running=False
        self.command_status.set(f'Synced {len(results)} character(s).'+(f' {len(errors)} need attention.' if errors else ''))
        self.refresh_command_center_views(force=True)
        if errors:
            chars=self._sso_characters(); lines=[]
            for cid,msg in errors:lines.append(f"{chars.get(str(cid),{}).get('character_name',cid)}: {msg}")
            messagebox.showwarning('Command Center sync','Some characters could not be synced. Older characters may need re-authorization for the expanded v3 scopes.\n\n'+'\n'.join(lines[:10]),parent=self)

    def _command_center_state_signature(self):
        """Cheap fingerprint of cached companion data used to avoid needless full re-renders."""
        chars=self._sso_characters(); cache=self._companion_cache(); parts=[]
        for key,rec in sorted(chars.items(),key=lambda kv:str(kv[0])):
            try:cid=int(rec.get('character_id') or key)
            except Exception:continue
            snap=cache.get(str(cid),{}) if isinstance(cache.get(str(cid),{}),dict) else {}
            parts.append((cid,str(snap.get('fetched_at') or ''),len(snap.get('assets') or []),len(snap.get('contracts') or []),len(snap.get('industry') or []),len(snap.get('skillqueue') or [])))
        return tuple(parts)

    def refresh_command_center_views(self,force=False):
        signature=self._command_center_state_signature()
        if not force and signature==self._command_center_snapshot_signature:
            # Selection metrics are cheap and may have changed even when the ESI cache did not.
            self.command_selected_changed(); self._skillplan_refresh_character_combo(); return
        chars=self._sso_characters(); cache=self._companion_cache()
        if self.command_char_tree is not None:
            self.command_char_tree.delete(*self.command_char_tree.get_children())
            for key,rec in sorted(chars.items(),key=lambda kv:str(kv[1].get('character_name','')).casefold()):
                try:cid=int(rec.get('character_id') or key)
                except Exception:continue
                snap=cache.get(str(cid),{}) if isinstance(cache.get(str(cid),{}),dict) else {}
                loc=snap.get('location') or {}; sysrow=system_by_id(loc.get('solar_system_id')) if loc else None
                ship=snap.get('ship') or {}; online=snap.get('online') or {}; wallet=snap.get('wallet'); clones=snap.get('clones') or {}
                clone_count=len(clones.get('jump_clones',[]) or []) if isinstance(clones,dict) else 0
                self.command_char_tree.insert('', 'end', iid=str(cid), values=(
                    rec.get('character_name',f'Character {cid}'), sysrow[1] if sysrow else '—', sysrow[7] if sysrow else '—',
                    type_name(ship.get('ship_type_id')) if ship else '—',clone_count if clones else '—','ONLINE' if online.get('online') else ('Offline' if online else '—'),
                    f'{float(wallet):,.0f}' if isinstance(wallet,(int,float)) else '—', self._format_sync_time(snap.get('fetched_at')) if snap else 'Never'))
        self.command_selected_changed(); self.refresh_asset_search(); self._refresh_contracts_jobs_alerts(); self._skillplan_refresh_character_combo()
        self._command_center_snapshot_signature=signature

    def command_selected_changed(self):
        cid=0
        if self.command_char_tree is not None and self.command_char_tree.selection():
            try:cid=int(self.command_char_tree.selection()[0])
            except Exception:cid=0
        if not cid:cid=int(self.esi_character_id or 0)
        snap=self._snapshot_for(cid); loc=snap.get('location') or {}; sr=system_by_id(loc.get('solar_system_id')) if loc else None; ship=snap.get('ship') or {}; online=snap.get('online') or {}; wallet=snap.get('wallet')
        self.command_metric_location.set((f'{sr[1]}\n{sr[7]}' if sr else '—'))
        self.command_metric_ship.set((f"{type_name(ship.get('ship_type_id'))}\n{ship.get('ship_name','')}" if ship else '—'))
        self.command_metric_wallet.set((f'{float(wallet):,.0f} ISK' if isinstance(wallet,(int,float)) else '—'))
        self.command_metric_online.set(('ONLINE\n'+self._iso_short(online.get('last_login')) if online and online.get('online') else ('OFFLINE\n'+self._iso_short(online.get('last_logout')) if online else '—')))
        clones=snap.get('clones') or {}
        if isinstance(clones,dict) and clones.get('home_location'):
            home=clones.get('home_location') or {}; self.command_status.set(f"Home clone: {self._snapshot_name(snap,home.get('location_id'),'location')} • {len(clones.get('jump_clones',[]) or [])} jump clone(s) cached.")

    def command_use_selected_character(self):
        if self.command_char_tree is None or not self.command_char_tree.selection():return
        try:cid=int(self.command_char_tree.selection()[0])
        except Exception:return
        self.use_character(cid,apply=True); self.command_selected_changed()

    def command_location_to_route(self):
        cid=0
        if self.command_char_tree is not None and self.command_char_tree.selection():
            try:cid=int(self.command_char_tree.selection()[0])
            except Exception:pass
        snap=self._snapshot_for(cid or self.esi_character_id); loc=snap.get('location') or {}; sr=system_by_id(loc.get('solar_system_id')) if loc else None
        if not sr:messagebox.showinfo('Command Center','Sync a character with location permission first.',parent=self);return
        self.route_from.set(sr[1]); self.quick_from.set(sr[1]); self.tabs.select(self.planner_tab)

    def _asset_price_map(self):
        cache=self.asset_price_cache if isinstance(self.asset_price_cache,dict) else {}
        prices=cache.get('prices',{}) if isinstance(cache.get('prices',{}),dict) else {}
        return prices

    def _asset_price(self,type_id):
        try:tid=str(int(type_id or 0))
        except Exception:return None
        value=self._asset_price_map().get(tid)
        try:
            price=float(value)
            return price if price>0 else None
        except Exception:return None

    def _format_isk_compact(self,value):
        try:v=float(value)
        except Exception:return '—'
        av=abs(v)
        if av>=1_000_000_000_000:return f'{v/1_000_000_000_000:.2f}t'
        if av>=1_000_000_000:return f'{v/1_000_000_000:.2f}b'
        if av>=1_000_000:return f'{v/1_000_000:.2f}m'
        if av>=1_000:return f'{v/1_000:.1f}k'
        return f'{v:,.0f}'

    def _asset_root_location(self,snap,asset,by_item=None):
        assets=snap.get('assets') or [] if isinstance(snap,dict) else []
        if by_item is None:
            by_item={int(a.get('item_id')):a for a in assets if isinstance(a,dict) and a.get('item_id')}
        seen=set(); current=asset
        for _ in range(16):
            if not isinstance(current,dict):return 0
            try:lid=int(current.get('location_id') or 0)
            except Exception:return 0
            ltype=str(current.get('location_type') or '').lower()
            if ltype=='item' and lid in by_item and lid not in seen:
                seen.add(lid); current=by_item[lid]; continue
            return lid
        return 0

    def _asset_system_row(self,snap,asset,by_item=None):
        lid=self._asset_root_location(snap,asset,by_item)
        if not lid:return None
        return self._resolved_location_system(snap,lid)

    def refresh_asset_market_prices(self,force=False):
        if self.asset_price_refresh_running:
            self.asset_value_status.set('Asset valuation refresh is already running…')
            return
        cache=self.asset_price_cache if isinstance(self.asset_price_cache,dict) else {}
        try:age=max(0,int(time.time())-int(cache.get('fetched_at',0) or 0)) if cache.get('fetched_at') else None
        except Exception:age=None
        if not force and age is not None and age<ASSET_PRICE_CACHE_SECONDS and cache.get('prices'):
            self.asset_value_status.set(f'Asset estimates: CCP market reference cache {age//60}m old • {len(cache.get("prices",{})):,} priced types.')
            return
        self.asset_price_refresh_running=True
        self.asset_value_status.set('Refreshing CCP market reference prices for asset valuation…')
        def work():
            try:
                data=fetch_asset_market_prices(); save_asset_market_price_cache(data)
                self.after(0,lambda d=data:self._asset_prices_loaded(d))
            except Exception as e:
                self.after(0,lambda msg=str(e):self._asset_prices_failed(msg))
        threading.Thread(target=work,daemon=True).start()

    def _command_center_visible(self):
        try:return str(self.tabs.nametowidget(self.tabs.select()))==str(self.command_tab)
        except Exception:return False

    def _asset_prices_loaded(self,data):
        self.asset_price_refresh_running=False; self.asset_price_cache=data
        stamp=self._market_time_text(data.get('fetched_at'))
        self.asset_value_status.set(f'Asset estimates refreshed {stamp} • {len(data.get("prices",{})):,} priced types • CCP average price with adjusted-price fallback.')
        if self._command_center_visible():self.refresh_asset_search()

    def _asset_prices_failed(self,error):
        self.asset_price_refresh_running=False
        cache=self.asset_price_cache if isinstance(self.asset_price_cache,dict) else {}
        if cache.get('prices'):
            self.asset_value_status.set(f'Could not refresh asset estimates ({error}). Using cached CCP reference prices.')
            if self._command_center_visible():self.refresh_asset_search()
        else:
            self.asset_value_status.set(f'Asset valuation unavailable: {error}. Asset grouping still works; ISK totals show —.')

    def _asset_tree_mousewheel(self,tree,event):
        try:
            steps=int(-event.delta/120)
            if steps==0:steps=-1 if event.delta>0 else 1
            tree.yview_scroll(steps,'units')
        except Exception:pass
        return 'break'

    def asset_system_context_menu(self,event):
        if self.asset_system_tree is None:return
        iid=self.asset_system_tree.identify_row(event.y)
        if iid:
            self.asset_system_tree.selection_set(iid)
            rec=self.asset_group_rows.get(iid,{})
            name=str(rec.get('system_name') or '')
            if name and system(name):self.show_system_context_menu(event,name)

    def asset_system_selected(self):
        if self.asset_system_tree is None or not self.asset_system_tree.selection():
            return
        iid=self.asset_system_tree.selection()[0]
        group=self.asset_group_rows.get(iid)
        if not group:return
        self._populate_asset_detail(group)

    def _populate_asset_detail(self,group):
        if self.asset_tree is None:return
        self.asset_tree.delete(*self.asset_tree.get_children()); self.asset_row_meta={}
        rows=group.get('rows',[]) if isinstance(group,dict) else []
        q=self.asset_search_var.get().strip().casefold()
        shown=0; visible_value=0.0; valued=0
        for idx,rec in enumerate(rows):
            name=rec.get('name','Unresolved EVE type')
            if q and q not in str(name).casefold() and q not in str(rec.get('pilot','')).casefold() and q not in str(rec.get('location','')).casefold():continue
            shown+=1
            if shown>1200:continue
            price=rec.get('unit_price'); total=rec.get('value')
            if total is not None:
                visible_value+=float(total); valued+=1
            iid=f"{rec.get('cid')}:{rec.get('asset_index')}"
            self.asset_row_meta[iid]={'cid':rec.get('cid'),'asset':rec.get('asset'),'type_id':rec.get('type_id')}
            self.asset_tree.insert('', 'end', iid=iid, values=(rec.get('pilot'),name,rec.get('qty'),rec.get('location'),rec.get('flag'),self._format_isk_compact(price) if price is not None else '—',self._format_isk_compact(total) if total is not None else '—'))
        full_value=group.get('value',0.0); full_valued=group.get('valued_stacks',0); full_stacks=group.get('stacks',0)
        self.asset_selected_summary.set(f"{group.get('system_name')} — {group.get('region')} • {group.get('pilots',0)} pilot(s) • {full_stacks:,} stacks • estimated {self._format_isk_compact(full_value)} ISK • valued {full_valued:,}/{full_stacks:,} stacks")
        extra=' Showing first 1,200.' if shown>1200 else ''
        self.asset_status.set(f'{shown:,} visible item stack(s) in selected system.'+extra+' Double-click an item to open its market details in EVE.')

    def refresh_asset_search(self):
        if self.asset_tree is None or self.asset_system_tree is None:return
        q=self.asset_search_var.get().strip().casefold()
        previous=None
        if self.asset_system_tree.selection():
            old=self.asset_group_rows.get(self.asset_system_tree.selection()[0],{})
            previous=old.get('key') if isinstance(old,dict) else None
        self.asset_system_tree.delete(*self.asset_system_tree.get_children()); self.asset_tree.delete(*self.asset_tree.get_children())
        self.asset_group_rows={}; self.asset_row_meta={}
        chars=self._sso_characters(); groups={}; total_stacks=0; total_units=0; grand_value=0.0; valued_stacks=0
        excluded_fitted_stacks=0; excluded_fitted_units=0; unresolved_root_stacks=0
        exclude_fitted=bool(self.asset_exclude_fitted_var.get())
        for key,rec in chars.items():
            try:cid=int(rec.get('character_id') or key)
            except Exception:continue
            snap=self._snapshot_for(cid); assets=snap.get('assets') or []
            by_item={int(a.get('item_id')):a for a in assets if isinstance(a,dict) and a.get('item_id')}
            for idx,a in enumerate(assets):
                if not isinstance(a,dict):continue
                try:qty=max(0,int(a.get('quantity',1) or 1))
                except Exception:qty=1
                if exclude_fitted and asset_flag_is_fitted(a.get('location_flag')):
                    excluded_fitted_stacks+=1; excluded_fitted_units+=qty
                    continue
                total_stacks+=1; total_units+=qty
                tid=int(a.get('type_id',0) or 0); name=type_name(tid); unit_price=self._asset_price(tid); value=(unit_price*qty) if unit_price is not None else None
                if value is not None:
                    grand_value+=value; valued_stacks+=1
                sr=self._asset_system_row(snap,a,by_item)
                if sr:
                    gkey=f'system:{int(sr[0])}'; sysname=sr[1]; region=sr[7]; sid=int(sr[0])
                else:
                    root=self._asset_root_location(snap,a,by_item)
                    unresolved_root_stacks+=1
                    gkey=f'unresolved:{root or 0}'; sysname=self._snapshot_name(snap,root,'location') if root else 'Unresolved / Other'; region='Location unresolved'; sid=0
                group=groups.setdefault(gkey,{'key':gkey,'system_id':sid,'system_name':sysname,'region':region,'pilot_ids':set(),'stacks':0,'units':0,'value':0.0,'valued_stacks':0,'rows':[],'matched':False})
                group['pilot_ids'].add(cid); group['stacks']+=1; group['units']+=qty
                if value is not None:group['value']+=value; group['valued_stacks']+=1
                location=self._asset_location_label(snap,a)
                pilot=str(rec.get('character_name',cid)); flag=str(a.get('location_flag','')).replace('_',' ')
                row={'cid':cid,'asset_index':idx,'asset':a,'type_id':tid,'name':name,'pilot':pilot,'qty':qty,'location':location,'flag':flag,'unit_price':unit_price,'value':value}
                group['rows'].append(row)
                if not q or q in name.casefold() or q in pilot.casefold() or q in location.casefold() or q in str(sysname).casefold() or q in str(region).casefold():group['matched']=True
        ordered=sorted((g for g in groups.values() if g.get('matched')),key=lambda g:(-float(g.get('value',0.0)),str(g.get('system_name','')).casefold()))
        selected_iid=None
        for n,g in enumerate(ordered):
            iid=f'asset-system-{n}'; g['pilots']=len(g.get('pilot_ids',set())); self.asset_group_rows[iid]=g
            self.asset_system_tree.insert('', 'end', iid=iid, values=(g['system_name'],g['region'],g['pilots'],f"{g['stacks']:,}",f"{g['units']:,}",self._format_isk_compact(g['value']) if g['valued_stacks'] else '—'))
            if previous and g.get('key')==previous:selected_iid=iid
        cache=self.asset_price_cache if isinstance(self.asset_price_cache,dict) else {}
        try:age=max(0,int(time.time())-int(cache.get('fetched_at',0) or 0)) if cache.get('fetched_at') else None
        except Exception:age=None
        freshness=(f'{age//60}m old' if age is not None else 'not loaded')
        coverage=(100.0*valued_stacks/total_stacks) if total_stacks else 0.0
        fitted_note=(f' • excluded {excluded_fitted_stacks:,} fitted stack(s)' if exclude_fitted and excluded_fitted_stacks else '')
        unresolved_note=(f' • {unresolved_root_stacks:,} stack(s) still in unresolved/restricted locations' if unresolved_root_stacks else '')
        self.asset_value_status.set(f'{len(groups):,} system/location group(s) • {total_stacks:,} stacks • {total_units:,} units • estimated {self._format_isk_compact(grand_value)} ISK • {coverage:.1f}% stacks valued • CCP reference prices {freshness}{fitted_note}{unresolved_note}.')
        if ordered:
            selected_iid=selected_iid or next(iter(self.asset_group_rows))
            self.asset_system_tree.selection_set(selected_iid); self.asset_system_tree.focus(selected_iid); self.asset_system_tree.see(selected_iid); self._populate_asset_detail(self.asset_group_rows[selected_iid])
        else:
            self.asset_selected_summary.set('No asset systems match the current search.')
            self.asset_status.set('Sync character assets or clear the search filter.')

    def open_selected_asset_market(self):
        if self.asset_tree is None or not self.asset_tree.selection():return
        meta=getattr(self,'asset_row_meta',{}).get(self.asset_tree.selection()[0],{}); tid=int(meta.get('type_id',0) or 0); cid=int(meta.get('cid',0) or self.esi_character_id or 0)
        if not tid:return
        def work():
            try:
                access,_=self._access_token_for_character(cid,ESI_OPEN_WINDOW_SCOPE); post_open_market_details(tid,access); self.after(0,lambda:self.status.set(f'Opened {type_name(tid)} in the EVE market.'))
            except Exception as e:self.after(0,lambda msg=str(e):messagebox.showerror('Open market in EVE',msg,parent=self))
        threading.Thread(target=work,daemon=True).start()

    def _refresh_contracts_jobs_alerts(self):
        chars=self._sso_characters()
        self.contract_row_meta={}
        for tree in getattr(self,'contract_trees',{}).values():tree.delete(*tree.get_children())
        if self.contract_items_tree is not None:self.contract_items_tree.delete(*self.contract_items_tree.get_children())
        if self.industry_tree is not None:self.industry_tree.delete(*self.industry_tree.get_children())
        if self.skillqueue_tree is not None:self.skillqueue_tree.delete(*self.skillqueue_tree.get_children())
        if self.alert_tree is not None:self.alert_tree.delete(*self.alert_tree.get_children())
        self.contract_detail_var.set('Select a contract to view details and item names.')
        alerts=[]; now=datetime.now(timezone.utc)
        settings=self.config.get('notification_settings',{}) if isinstance(self.config.get('notification_settings',{}),dict) else {}
        ind_hours=float(settings.get('industry_hours',2) or 2); queue_hours=float(settings.get('skillqueue_hours',24) or 24)
        for key,rec in chars.items():
            try:cid=int(rec.get('character_id') or key)
            except Exception:continue
            name=str(rec.get('character_name') or cid); snap=self._snapshot_for(cid)
            for idx,c in enumerate(snap.get('contracts') or []):
                iid=f'{cid}:{idx}'; self.contract_row_meta[iid]={'cid':cid,'contract':c,'snapshot':snap}
                start_name=self._snapshot_name(snap,c.get('start_location_id'),'location'); end_name=self._snapshot_name(snap,c.get('end_location_id'),'location')
                ctype=contract_type_name(c.get('type')); status=contract_status_name(c.get('status')); bucket=contract_status_bucket(c.get('status'))
                title=str(c.get('title') or '').strip() or ctype
                tree=getattr(self,'contract_trees',{}).get(bucket)
                if tree is not None:
                    tree.insert('', 'end', iid=iid, values=(name,title,ctype,status,start_name,end_name,self.format_isk(c.get('reward')),self.format_isk(c.get('collateral')),self._iso_short(c.get('date_expired'))))
            jobs=snap.get('industry_jobs') or []
            for idx,j in enumerate(jobs):
                end=j.get('end_date'); activity=industry_activity_name(j.get('activity_id')); bp=type_name(j.get('blueprint_type_id') or j.get('product_type_id'))
                facility=self._snapshot_name(snap,j.get('facility_id') or j.get('station_id'),'location')
                if self.industry_tree is not None:self.industry_tree.insert('', 'end', values=(name,activity,bp,facility,str(j.get('status','')).replace('_',' ').title(),self._iso_short(end)))
                try:
                    dt=datetime.fromisoformat(str(end).replace('Z','+00:00'))
                    hrs=(dt-now).total_seconds()/3600
                    if 0<=hrs<=ind_hours:alerts.append(('INFO',name,f'Industry job completes in {hrs:.1f}h: {bp}',self._iso_short(end)))
                except Exception:pass
            queue=snap.get('skillqueue') or []
            if not queue and snap:
                if snap.get('skillqueue') is not None:alerts.append(('WARN',name,'Skill queue is empty','Now'))
            for q in queue[:20]:
                finish=q.get('finish_date'); sk=type_name(q.get('skill_id'))
                if self.skillqueue_tree is not None:self.skillqueue_tree.insert('', 'end', values=(name,sk,q.get('finished_level',''),self._iso_short(finish)))
            if queue:
                final=queue[-1].get('finish_date')
                try:
                    dt=datetime.fromisoformat(str(final).replace('Z','+00:00')); hrs=(dt-now).total_seconds()/3600
                    if 0<=hrs<=queue_hours:alerts.append(('INFO',name,f'Skill queue ends in {hrs:.1f}h',self._iso_short(final)))
                except Exception:pass
        op=self._get_active_operation()
        if op:
            for item in op.get('_fuel_alerts',[]) if isinstance(op.get('_fuel_alerts',[]),list) else []:alerts.append(tuple(item))
        if self.alert_tree is not None:
            for row in alerts:self.alert_tree.insert('', 'end', values=row)

    def _skillplan_character_options(self):
        chars=self._sso_characters(); out=[]
        for key,rec in sorted(chars.items(),key=lambda kv:str(kv[1].get('character_name','')).casefold()):
            try:cid=int(rec.get('character_id') or key)
            except Exception:continue
            out.append((f"{rec.get('character_name',cid)}",cid))
        return out

    def _skillplan_selected_cid(self):
        label=self.skillplan_character.get().strip()
        for name,cid in self._skillplan_character_options():
            if name==label:return cid
        return int(self.esi_character_id or 0)

    def _skillplan_refresh_character_combo(self):
        if not hasattr(self,'skillplan_character_combo'):return
        opts=self._skillplan_character_options(); names=[n for n,_ in opts]
        self.skillplan_character_combo.configure(values=names)
        current=self._skillplan_selected_cid()
        chosen=next((n for n,c in opts if c==current),names[0] if names else 'Active character')
        self.skillplan_character.set(chosen)

    @staticmethod
    def _queue_seconds(row):
        if not isinstance(row,dict):return 10**18
        for start_key in ('start_date','training_start_date'):
            start=row.get(start_key); finish=row.get('finish_date')
            if start and finish:
                try:
                    a=datetime.fromisoformat(str(start).replace('Z','+00:00')); b=datetime.fromisoformat(str(finish).replace('Z','+00:00'))
                    return max(1.0,(b-a).total_seconds())
                except Exception:pass
        return 10**18

    @staticmethod
    def _duration_text(seconds):
        try:sec=int(seconds)
        except Exception:return 'Unknown'
        if sec>=10**17:return 'Unknown'
        d,sec=divmod(sec,86400); h,sec=divmod(sec,3600); m,_=divmod(sec,60)
        if d:return f'{d}d {h}h {m}m'
        if h:return f'{h}h {m}m'
        return f'{m}m'

    def _trained_skill_levels(self,snap):
        payload=(snap or {}).get('skills_full') or {}
        out={}
        for row in payload.get('skills',[]) if isinstance(payload,dict) else []:
            try:out[int(row.get('skill_id'))]=int(row.get('trained_skill_level',0) or 0)
            except Exception:pass
        return out

    def _skillplan_prereq_text(self,skill_id):
        reqs=skill_requirements(skill_id)
        return ', '.join(f'{type_name(r)} {lvl}' for r,lvl in reqs) if reqs else 'None'

    def _skillplan_validate_order(self,rows,snap):
        trained=self._trained_skill_levels(snap); achieved=dict(trained); problems={}
        for idx,row in enumerate(rows):
            sid=int(row.get('skill_id',0) or 0); lvl=int(row.get('finished_level',0) or 0); miss=[]
            # Lower levels of the same skill must necessarily precede higher levels.
            if lvl>1 and achieved.get(sid,0)<lvl-1:miss.append(f'{type_name(sid)} {lvl-1}')
            for rid,rlvl in skill_requirements(sid):
                if achieved.get(rid,0)<rlvl:miss.append(f'{type_name(rid)} {rlvl}')
            if miss:problems[idx]=miss
            achieved[sid]=max(achieved.get(sid,0),lvl)
        return problems

    def _skillplan_render(self):
        if self.skillplan_tree is None:return
        self.skillplan_tree.delete(*self.skillplan_tree.get_children())
        cid=self._skillplan_selected_cid(); snap=self._snapshot_for(cid); problems=self._skillplan_validate_order(self.skillplan_rows,snap)
        total=0.0; known=0
        for idx,row in enumerate(self.skillplan_rows):
            sid=int(row.get('skill_id',0) or 0); lvl=int(row.get('finished_level',0) or 0); seconds=self._queue_seconds(row)
            if seconds<10**17:total+=seconds; known+=1
            status='BLOCKED' if idx in problems else ('TRAINING' if idx==0 and row.get('start_date') else 'Ready')
            prereq=self._skillplan_prereq_text(sid)
            if idx in problems:prereq='Missing before this: '+', '.join(problems[idx])
            self.skillplan_tree.insert('', 'end', iid=str(idx),values=(idx+1,type_name(sid),lvl,self._duration_text(seconds),prereq,status))
        h=int(total//3600); d,h=divmod(h,24)
        self.skillplan_summary.set(f'{len(self.skillplan_rows)} queue item(s) • {d}d {h}h known training time • {len(problems)} ordering issue(s)')
        if problems:self.skillplan_status.set('Dependency warning: one or more prerequisites are not trained or are later in the plan.')
        elif self.skillplan_rows:self.skillplan_status.set('Plan is dependency-valid against synced trained skills and CCP SDE prerequisites.')

    def skillplan_import(self):
        self._skillplan_refresh_character_combo(); cid=self._skillplan_selected_cid(); snap=self._snapshot_for(cid)
        queue=snap.get('skillqueue') if isinstance(snap,dict) else None
        if queue is None:
            messagebox.showinfo('Skill Queue Planner','Sync this character in Command Center first. The character also needs the skill queue and skills permissions.',parent=self);return
        try:ensure_type_names([q.get('skill_id') for q in queue or [] if isinstance(q,dict)])
        except Exception:pass
        self.skillplan_original=[dict(q) for q in (queue or []) if isinstance(q,dict)]
        self.skillplan_original.sort(key=lambda r:int(r.get('queue_position')) if r.get('queue_position') is not None else 999999)
        self.skillplan_rows=[dict(q) for q in self.skillplan_original]
        self._skillplan_render()
        self.skillplan_status.set('Imported current EVE queue. Optimise to reorder the remaining items shortest-first legally.')

    def skillplan_reset(self):
        self.skillplan_rows=[dict(q) for q in self.skillplan_original]; self._skillplan_render(); self.skillplan_status.set('Restored the imported EVE queue order.')

    def _skillplan_edges(self,rows,snap):
        trained=self._trained_skill_levels(snap); n=len(rows); edges=[set() for _ in range(n)]; indeg=[0]*n
        # Map queued skill levels to row indexes.
        by_skill={}
        for i,r in enumerate(rows):
            try:sid=int(r.get('skill_id')); lvl=int(r.get('finished_level'))
            except Exception:continue
            by_skill.setdefault(sid,[]).append((lvl,i))
        for sid,lst in by_skill.items():
            lst.sort()
            for (la,ia),(lb,ib) in zip(lst,lst[1:]):
                if ia!=ib and ib not in edges[ia]:edges[ia].add(ib);indeg[ib]+=1
        missing=[]
        for i,r in enumerate(rows):
            try:sid=int(r.get('skill_id')); lvl=int(r.get('finished_level'))
            except Exception:continue
            for rid,rlvl in skill_requirements(sid):
                if trained.get(rid,0)>=rlvl:continue
                candidates=[(qlvl,j) for qlvl,j in by_skill.get(rid,[]) if qlvl>=rlvl]
                if candidates:
                    _,j=min(candidates)
                    if i!=j and i not in edges[j]:edges[j].add(i);indeg[i]+=1
                else:missing.append((i,rid,rlvl))
            if lvl>1 and trained.get(sid,0)<lvl-1:
                candidates=[(qlvl,j) for qlvl,j in by_skill.get(sid,[]) if qlvl>=lvl-1 and qlvl<lvl]
                if candidates:
                    _,j=max(candidates)
                    if i!=j and i not in edges[j]:edges[j].add(i);indeg[i]+=1
                elif trained.get(sid,0)<lvl-1:missing.append((i,sid,lvl-1))
        return edges,indeg,missing

    def skillplan_optimise(self):
        if not self.skillplan_rows:self.skillplan_import()
        if not self.skillplan_rows:return
        cid=self._skillplan_selected_cid(); snap=self._snapshot_for(cid)
        rows=[dict(r) for r in self.skillplan_rows]; edges,indeg,missing=self._skillplan_edges(rows,snap)
        # Never move a currently training item behind another item.
        locked=None
        if rows and (rows[0].get('start_date') or rows[0].get('training_start_date')):locked=0
        import heapq
        heap=[]
        for i,d in enumerate(indeg):
            if d==0 and i!=locked:heapq.heappush(heap,(self._queue_seconds(rows[i]),i))
        order=[]
        if locked is not None:
            order.append(locked)
            for j in edges[locked]:
                indeg[j]-=1
                if indeg[j]==0:heapq.heappush(heap,(self._queue_seconds(rows[j]),j))
        while heap:
            _,i=heapq.heappop(heap); order.append(i)
            for j in edges[i]:
                indeg[j]-=1
                if indeg[j]==0:heapq.heappush(heap,(self._queue_seconds(rows[j]),j))
        if len(order)!=len(rows):
            self.skillplan_status.set('Could not optimise: prerequisite graph contains an unresolved cycle. Refresh EVE data and try again.');return
        self.skillplan_rows=[rows[i] for i in order]; self._skillplan_render()
        if missing:
            uniq=[]
            for _,sid,lvl in missing:
                label=f'{type_name(sid)} {lvl}'
                if label not in uniq:uniq.append(label)
            self.skillplan_status.set('Optimised legal order for queued items. Missing prerequisite not in queue/trained: '+', '.join(uniq[:5])+('…' if len(uniq)>5 else ''))
        else:self.skillplan_status.set('Optimised shortest-first using a prerequisite-aware topological sort. Current training item remains locked first.')

    def skillplan_move(self,direction):
        if self.skillplan_tree is None or not self.skillplan_tree.selection():return
        try:i=int(self.skillplan_tree.selection()[0])
        except Exception:return
        j=i+int(direction)
        if j<0 or j>=len(self.skillplan_rows):return
        rows=[dict(r) for r in self.skillplan_rows]; rows[i],rows[j]=rows[j],rows[i]
        problems=self._skillplan_validate_order(rows,self._snapshot_for(self._skillplan_selected_cid()))
        if problems:
            self.skillplan_status.set('Move blocked: that order would put a skill before one of its prerequisites.');return
        self.skillplan_rows=rows; self._skillplan_render(); self.skillplan_tree.selection_set(str(j)); self.skillplan_tree.see(str(j))

    def skillplan_copy(self):
        if not self.skillplan_rows:return
        # EVE's clipboard skill-plan importer expects one plain "Skill Name level"
        # entry per line. Do not include display-only list numbers or training-time
        # annotations because the client treats those as part of the skill name and
        # reports the line as unrecognised.
        lines=[]
        for r in self.skillplan_rows:
            try:lvl=int(r.get('finished_level',0) or 0)
            except Exception:lvl=0
            name=str(type_name(r.get('skill_id')) or '').strip()
            if name and lvl>0:lines.append(f"{name} {lvl}")
        if not lines:
            self.skillplan_status.set('Nothing valid to copy for EVE. Refresh the imported queue and try again.');return
        self.clipboard_clear(); self.clipboard_append('\n'.join(lines)); self.update_idletasks()
        self.skillplan_status.set(f'Copied {len(lines)} EVE-compatible skill line(s) — list numbers and training-time notes removed.')

    def _selected_contract_meta(self):
        for tree in getattr(self,'contract_trees',{}).values():
            sel=tree.selection()
            if sel:return self.contract_row_meta.get(sel[0],{})
        return {}

    def contract_selected_changed(self,tree=None):
        if tree is not None:
            self.contract_tree=tree
            for other in getattr(self,'contract_trees',{}).values():
                if other is not tree:
                    try:other.selection_remove(other.selection())
                    except Exception:pass
        meta=self._selected_contract_meta(); c=meta.get('contract') or {}; snap=meta.get('snapshot') or {}; cid=int(meta.get('cid',0) or 0)
        if not c:
            self.contract_detail_var.set('Select a contract to view details and item names.'); return
        issuer=self._snapshot_name(snap,c.get('issuer_id'),'entity'); assignee=self._snapshot_name(snap,c.get('assignee_id'),'entity') if c.get('assignee_id') else CONTRACT_AVAILABILITY_NAMES.get(str(c.get('availability','')).lower(),'Public')
        ctype=contract_type_name(c.get('type')); status=contract_status_name(c.get('status'))
        self.contract_detail_var.set(f'{ctype} • {status} • Issuer: {issuer} • Assigned: {assignee}')
        cache=(snap.get('contract_items') or {}) if isinstance(snap,dict) else {}
        items=cache.get(str(c.get('contract_id'))) if isinstance(cache,dict) else None
        if isinstance(items,list):self._render_contract_items(items)
        elif self.contract_items_tree is not None:self.contract_items_tree.delete(*self.contract_items_tree.get_children())

    def _render_contract_items(self,items):
        if self.contract_items_tree is None:return
        try:ensure_type_names([r.get('type_id') for r in items or [] if isinstance(r,dict)])
        except Exception:pass
        self.contract_items_tree.delete(*self.contract_items_tree.get_children())
        for row in items or []:
            name=type_name(row.get('type_id')); qty=int(row.get('quantity',0) or 0)
            side='Included' if bool(row.get('is_included')) else 'Requested'
            state='Singleton' if bool(row.get('is_singleton')) else 'Stack'
            self.contract_items_tree.insert('', 'end', values=(name,qty,side,state))

    def load_selected_contract_items(self):
        meta=self._selected_contract_meta(); c=meta.get('contract') or {}; cid=int(meta.get('cid',0) or 0); contract_id=int(c.get('contract_id',0) or 0)
        if not cid or not contract_id:return
        snap=self._snapshot_for(cid); cache=snap.setdefault('contract_items',{}) if isinstance(snap,dict) else {}
        if isinstance(cache,dict) and isinstance(cache.get(str(contract_id)),list):self._render_contract_items(cache[str(contract_id)]);return
        self.contract_detail_var.set('Loading contract items from CCP ESI…')
        def work():
            try:
                access,_=self._access_token_for_character(cid,ESI_CONTRACTS_SCOPE); items=fetch_contract_items(cid,contract_id,access)
                try:ensure_type_names([r.get('type_id') for r in items or [] if isinstance(r,dict)])
                except Exception:pass
                snap=self._snapshot_for(cid); snap.setdefault('contract_items',{})[str(contract_id)]=items; save_config(self.config)
                self.after(0,lambda:self._finish_contract_items(items,cid,contract_id))
            except Exception as e:self.after(0,lambda msg=str(e):messagebox.showerror('Contract items',msg,parent=self))
        threading.Thread(target=work,daemon=True).start()

    def _finish_contract_items(self,items,cid,contract_id):
        self._render_contract_items(items); self.contract_detail_var.set(f'{len(items):,} contract item row(s) loaded with EVE item names.')

    def open_selected_contract(self):
        meta=self._selected_contract_meta(); c=meta.get('contract') or {}; cid=int(meta.get('cid',0) or 0); contract_id=int(c.get('contract_id',0) or 0)
        if not c:return
        if not cid or not contract_id:return
        def work():
            try:
                access,_=self._access_token_for_character(cid,ESI_OPEN_WINDOW_SCOPE); post_open_contract(contract_id,access); self.after(0,lambda:self.status.set(f'Opened contract {contract_id} in EVE.'))
            except Exception as e:self.after(0,lambda msg=str(e):messagebox.showerror('Open contract in EVE',msg,parent=self))
        threading.Thread(target=work,daemon=True).start()

    def plan_selected_contract(self):
        meta=self._selected_contract_meta(); c=meta.get('contract') or {}
        if not c:return
        snap=meta.get('snapshot') or self._snapshot_for(meta.get('cid',0)); a=self._resolved_location_system(snap,c.get('start_location_id')); b=self._resolved_location_system(snap,c.get('end_location_id'))
        if not a or not b:
            messagebox.showinfo('Contract route','The start or destination could not be resolved to a solar system. Re-sync the character; restricted player structures may also require the structure-read permission and docking access.',parent=self);return
        self.route_from.set(a[1]); self.route_to.set(b[1]); self.tabs.select(self.planner_tab); self.find_route()

    # -------------------- v3.1 Hunting / Roam Intelligence --------------------
    def _hunting_cache_age(self):
        try:ts=int(self.hunting_data.get('fetched_at',0) or 0)
        except Exception:ts=0
        return max(0,int(time.time())-ts) if ts else None

    def refresh_hunting_intel(self,force=False):
        if self.hunting_refresh_running:return
        age=self._hunting_cache_age()
        stale_sov=bool(self.hunting_data.get('sovereignty_error')) or ('sovereignty/systems' not in str(self.hunting_data.get('source','')))
        if not force and not stale_sov and age is not None and age<300:
            self.scan_hunting_area(use_cached=True); return
        self.hunting_refresh_running=True; self.hunt_status.set('Refreshing last-hour hunting intel from CCP ESI…')
        def work():
            try:data=fetch_hunting_intel(); self.after(0,lambda d=data:self._finish_hunting_intel(d,None))
            except Exception as e:self.after(0,lambda msg=str(e):self._finish_hunting_intel(None,msg))
        threading.Thread(target=work,daemon=True).start()

    def _finish_hunting_intel(self,data,error):
        self.hunting_refresh_running=False
        if error:
            self.hunt_status.set('Hunting intel refresh failed: '+error)
            if self.hunting_data:self.scan_hunting_area(use_cached=True)
            return
        self.hunting_data=data or {}; self.config['hunting_cache']=self.hunting_data
        # Keep Capital Ops activity context on the same fresh CCP snapshot.
        self.activity_data={'systems':dict(self.hunting_data.get('systems',{})),'fetched_at':self.hunting_data.get('fetched_at'),'source':'CCP ESI via Hunting Intel'}
        self.config['activity_cache']=self.activity_data; save_config(self.config)
        self.scan_hunting_area(use_cached=True)

    def _hunt_selected_system(self):
        if self.hunt_tree is None or not self.hunt_tree.selection():return ''
        vals=self.hunt_tree.item(self.hunt_tree.selection()[0],'values')
        return str(vals[1]) if len(vals)>1 else ''

    def _ess_observation(self,system_name):
        rec=self.ess_observations.get(str(system_name).casefold(),{})
        return rec if isinstance(rec,dict) else {}

    def _ess_text(self,system_name,ess_candidate):
        obs=self._ess_observation(system_name); main=float(obs.get('main_bank',0) or 0); reserve=float(obs.get('reserve_bank',0) or 0)
        if main>0 or reserve>0:
            bits=[]
            if main>0:bits.append('M '+format_isk_short(main))
            if reserve>0:bits.append('R '+format_isk_short(reserve))
            return ' / '.join(bits)
        return 'Potential' if ess_candidate else '—'

    def scan_hunting_area(self,use_cached=False):
        origin_name=self.hunt_origin.get().strip(); origin=system(origin_name)
        if not origin:
            messagebox.showwarning('Hunting','Choose a valid origin system from autocomplete first.',parent=self); return
        if not database_schema_ready():
            messagebox.showinfo('Hunting','Update EVE data first so the stargate graph is available.',parent=self); return
        if not use_cached and not self.hunting_data:
            self.refresh_hunting_intel(True); return
        try:max_hops=max(1,min(30,int(self.hunt_max_hops.get())))
        except Exception:max_hops=10; self.hunt_max_hops.set(10)
        origin,nearby=gate_neighborhood(origin_name,max_hops)
        systems_data=self.hunting_data.get('systems',{}) if isinstance(self.hunting_data,dict) else {}
        sov_data=self.hunting_data.get('sovereignty',{}) if isinstance(self.hunting_data,dict) else {}
        mode=self.hunt_mode.get(); sec_mode=self.hunt_security.get(); min_npc=max(0,int(self.hunt_min_npc.get() or 0)); rows=[]
        for node,hops in nearby:
            if int(node[0])==int(origin[0]):continue
            sec=float(node[5]); band=security_band(sec)
            if sec_mode=='Low + Null' and band=='High-sec':continue
            if sec_mode=='Null only' and band!='Null-sec':continue
            rec=systems_data.get(str(node[0]),{}) if isinstance(systems_data,dict) else {}
            npc=int(rec.get('npc_kills',0) or 0); ships=int(rec.get('ship_kills',0) or 0); pods=int(rec.get('pod_kills',0) or 0); traffic=int(rec.get('ship_jumps',0) or 0)
            if npc<min_npc:continue
            sov=sov_data.get(str(node[0]),{}) if isinstance(sov_data,dict) else {}; has_sov=bool(int(sov.get('alliance_id',0) or 0) or int(sov.get('corporation_id',0) or 0))
            ess_candidate=bool(sec<=0.0 and has_sov)
            obs=self._ess_observation(node[1]); observed_main=float(obs.get('main_bank',0) or 0)
            score=hunting_score(mode,rec,sec,has_sov,observed_main)
            rows.append({'node':node,'hops':hops,'npc':npc,'ships':ships,'pods':pods,'traffic':traffic,'score':score,'ess_candidate':ess_candidate,'has_sov':has_sov,'ess_text':self._ess_text(node[1],ess_candidate)})
        rows.sort(key=lambda r:(-r['score'],r['hops'],-r['npc'],r['node'][1].casefold()))
        self.hunt_results=rows
        if self.hunt_tree is not None:
            self.hunt_tree.delete(*self.hunt_tree.get_children())
            for i,r in enumerate(rows,1):
                n=r['node']; tags=()
                if r['ess_candidate'] and mode=='ESS Hunt':tags=('ess',)
                elif r['ships']+r['pods']>=5:tags=('danger',)
                elif r['npc']>=250:tags=('hot',)
                self.hunt_tree.insert('', 'end', iid=str(n[0]), values=(i,n[1],n[7],r['hops'],f'{float(n[5]):.2f}',r['traffic'],r['npc'],r['ships'],r['pods'],r['score'],r['ess_text'],'YES' if r['has_sov'] else '—'),tags=tags)
        self.hunt_metric_systems.set(f'{len(rows):,}\nwithin {max_hops} hops')
        rat=max(rows,key=lambda r:r['npc'],default=None); pvp=max(rows,key=lambda r:(r['ships']*2+r['pods']*3),default=None)
        ess=max((r for r in rows if r['ess_candidate']),key=lambda r:(float(self._ess_observation(r['node'][1]).get('main_bank',0) or 0),r['npc'],r['score']),default=None)
        self.hunt_metric_ratting.set(f"{rat['node'][1]}\n{rat['npc']:,} NPC kills/h" if rat and rat['npc'] else 'No signal')
        self.hunt_metric_pvp.set(f"{pvp['node'][1]}\n{pvp['ships']} ship • {pvp['pods']} pod" if pvp and (pvp['ships'] or pvp['pods']) else 'No signal')
        self.hunt_metric_ess.set(f"{ess['node'][1]}\n{ess['ess_text']}" if ess else 'No sov-null target')
        age=self._hunting_cache_age(); stamp=f'{age//60}m old' if age is not None else 'no timestamp'
        sov_note='Sovereignty feed unavailable; ESS potential disabled. ' if self.hunting_data.get('sovereignty_error') else ''
        self.hunt_status.set(f'{mode} scan from {origin[1]} • {len(rows):,} candidate systems • CCP last-hour activity cache {stamp}. {sov_note}Traffic is jumps/hour; it is not an exact pilot count. ESS “Potential” means sovereign nullsec + ratting signal, not a public bank balance.')

    def hunt_tree_context_menu(self,event):
        if self.hunt_tree is None:return
        iid=self.hunt_tree.identify_row(event.y)
        if not iid:return
        self.hunt_tree.selection_set(iid); self.hunt_tree.focus(iid)
        vals=self.hunt_tree.item(iid,'values')
        if vals:self.show_system_context_menu(event,str(vals[1]))

    def hunt_set_selected_destination(self):
        name=self._hunt_selected_system()
        if name:self.set_eve_destination(name)

    def hunt_use_selected_origin(self):
        name=self._hunt_selected_system()
        if not name:return
        self.hunt_origin.set(name); self.scan_hunting_area(use_cached=True)

    def hunt_record_selected_ess(self):
        name=self._hunt_selected_system()
        if not name:return
        old=self._ess_observation(name); old_main=float(old.get('main_bank',0) or 0)/1e6; old_res=float(old.get('reserve_bank',0) or 0)/1e6
        main=simpledialog.askfloat('Observed ESS Main Bank',f'Enter the ESS Main Bank value you observed in {name}, in millions of ISK:',initialvalue=old_main if old_main else None,minvalue=0,parent=self)
        if main is None:return
        reserve=simpledialog.askfloat('Observed ESS Reserve Bank',f'Optional: enter the Reserve Bank value observed in {name}, in millions of ISK. Use 0 if unknown:',initialvalue=old_res if old_res else 0,minvalue=0,parent=self)
        if reserve is None:reserve=0
        self.ess_observations[name.casefold()]={'system':name,'main_bank':float(main)*1e6,'reserve_bank':float(reserve)*1e6,'observed_at':int(time.time()),'source':'manual in-game observation'}
        self.config['ess_observations']=self.ess_observations; save_config(self.config); self.scan_hunting_area(use_cached=True)

    def hunt_clear_selected_ess(self):
        name=self._hunt_selected_system()
        if not name:return
        self.ess_observations.pop(name.casefold(),None); self.config['ess_observations']=self.ess_observations; save_config(self.config); self.scan_hunting_area(use_cached=True)

    # -------------------- v3 Capital Operations --------------------
    def _get_active_operation(self):
        name=self.active_operation_name or self.operation_name.get().strip()
        op=self.operations.get(name) if name else None
        return op if isinstance(op,dict) else None

    def _save_operations(self):
        self.config['operations']=self.operations; self.config['active_operation']=self.active_operation_name; save_config(self.config)

    def create_operation_from_route(self):
        if len(self.last_route_nodes)<2:
            if self.route_from.get().strip() and self.route_to.get().strip():self.find_route()
        if len(self.last_route_nodes)<2:
            messagebox.showinfo('Capital Operations','Calculate a route first.',parent=self);return
        name=self.operation_name.get().strip() or f'{self.last_route_nodes[0][1]} → {self.last_route_nodes[-1][1]}'
        old=self.operations.get(name,{}) if isinstance(self.operations.get(name,{}),dict) else {}
        route=[n[1] for n in self.last_route_nodes]
        oldlegs=old.get('legs',[]) if old.get('route')==route else []
        legs=[]
        for i in range(len(route)-1):
            prev=oldlegs[i] if i<len(oldlegs) and isinstance(oldlegs[i],dict) else {}
            legs.append({'status':prev.get('status','PENDING'),'cyno_pilot_id':int(prev.get('cyno_pilot_id',0) or 0),'role':prev.get('role','PRIMARY'),'note':prev.get('note','')})
        op={'name':name,'route':route,'legs':legs,'manifest':old.get('manifest',[]) if isinstance(old.get('manifest',[]),list) else [],'created_utc':old.get('created_utc') or datetime.now(timezone.utc).isoformat(),'updated_utc':datetime.now(timezone.utc).isoformat(),'route_settings':{'security':self.route_sec.get(),'mode':self.route_mode.get(),'station_policy':self.route_station_policy.get(),'enforce_legality':bool(self.enforce_legality.get())}}
        self.operations[name]=op; self.active_operation_name=name; self.operation_name.set(name); self._save_operations(); self.tabs.select(self.operations_tab); self.refresh_operation_ui(); self.operation_status.set(f'Operation saved: {name}')

    def load_operation_dialog(self):
        if not self.operations:messagebox.showinfo('Capital Operations','No saved operations yet.',parent=self);return
        names=sorted(self.operations); prompt='Enter an operation name:\n\n'+'\n'.join(names[:20])
        name=simpledialog.askstring('Load operation',prompt,parent=self,initialvalue=self.active_operation_name or names[0])
        if not name:return
        match=next((x for x in names if x.casefold()==name.strip().casefold()),None)
        if not match:messagebox.showwarning('Load operation','Operation not found.',parent=self);return
        self.active_operation_name=match; self.operation_name.set(match); self._save_operations(); self.refresh_operation_ui()

    def _operation_route_nodes(self,op=None):
        op=op or self._get_active_operation()
        if not op:return []
        nodes=[]
        for name in op.get('route',[]):
            n=system(name)
            if not n:return []
            nodes.append(n)
        return nodes

    def _activity_record(self,system_id):
        systems=self.activity_data.get('systems',{}) if isinstance(self.activity_data,dict) else {}
        return systems.get(str(int(system_id)),{}) if isinstance(systems,dict) else {}

    def refresh_operation_ui(self):
        op=self._get_active_operation()
        if self.operation_route_tree is not None:self.operation_route_tree.delete(*self.operation_route_tree.get_children())
        if self.operation_manifest_tree is not None:self.operation_manifest_tree.delete(*self.operation_manifest_tree.get_children())
        if not op:
            self.operation_next_summary.set('NEXT JUMP —'); self.operation_fuel_summary.set('No operation loaded.');return
        nodes=self._operation_route_nodes(op); chars=self._sso_characters(); legs=op.get('legs',[])
        for i in range(max(0,len(nodes)-1)):
            a,b=nodes[i],nodes[i+1]; meta=legs[i] if i<len(legs) else {}; rec=self._activity_record(b[0]); score=activity_score(rec); cid=int(meta.get('cyno_pilot_id',0) or 0); pilot=chars.get(str(cid),{}).get('character_name','') if cid else ''
            status=str(meta.get('status','PENDING')); role=str(meta.get('role','PRIMARY')); note=str(meta.get('note',''))
            self.operation_route_tree.insert('', 'end', iid=str(i), values=(i+1,a[1],b[1],b[7],f'{distance_ly(a,b):.3f}',int(b[8] or 0) if len(b)>8 else 0,score,status,pilot or '—',role,note),tags=('done',) if status=='DONE' else (('hot',) if score>=75 else ()))
        self.operation_route_tree.tag_configure('done',foreground='#6f8799'); self.operation_route_tree.tag_configure('hot',background='#2a1818',foreground='#ffb1aa')
        self._refresh_operation_manifest(op,nodes); self._refresh_operation_next(op,nodes); self._refresh_contracts_jobs_alerts()

    def _operation_pilot_skills(self,pilot_id,ship):
        rec=self._sso_characters().get(str(int(pilot_id or 0)),{}) if pilot_id else {}; sk=rec.get('skills',{}) if isinstance(rec.get('skills',{}),dict) else {}
        try:jdc=int(sk.get('Jump Drive Calibration',self.jdc.get()))
        except Exception:jdc=self.jdc.get()
        try:jfc=int(sk.get('Jump Fuel Conservation',self.jfc.get()))
        except Exception:jfc=self.jfc.get()
        try:jf=int(sk.get('Jump Freighters',self.jf.get())) if ship.get('jf_bonus') else 0
        except Exception:jf=self.jf.get() if ship.get('jf_bonus') else 0
        return jdc,jfc,jf

    def _owned_isotope_totals(self):
        totals={name:0 for name in ISOTOPE_TYPE_IDS}
        wanted={tid:name for name,tid in ISOTOPE_TYPE_IDS.items()}
        for snap in self._companion_cache().values():
            if not isinstance(snap,dict):continue
            for a in snap.get('assets') or []:
                try:tid=int(a.get('type_id',0));qty=int(a.get('quantity',0) or 0)
                except Exception:continue
                if tid in wanted:totals[wanted[tid]]+=max(0,qty)
        return totals

    def _refresh_operation_manifest(self,op,nodes):
        manifest=op.get('manifest',[]) if isinstance(op.get('manifest',[]),list) else []; owned=self._owned_isotope_totals(); chars=self._sso_characters(); route_ds=[distance_ly(nodes[i],nodes[i+1]) for i in range(len(nodes)-1)]
        required={name:0 for name in ISOTOPE_TYPE_IDS}; total_cost=0.0; alerts=[]
        for idx,item in enumerate(manifest):
            shipname=normalize_ship_name(item.get('ship','Rhea')); sh=SHIPS.get(shipname,SHIPS['Rhea']); qty=max(1,int(item.get('qty',1) or 1)); pid=int(item.get('pilot_id',0) or 0); jdc,jfc,jf=self._operation_pilot_skills(pid,sh); maxr=sh['range']*(1+0.2*jdc); viable=all(d<=maxr+1e-9 for d in route_ds)
            fuel=sum(calc_fuel(d,sh,jfc,jf) for d in route_ds)*qty; iso=sh['isotope']; required[iso]+=fuel; cost=self.fuel_cost(iso,fuel); total_cost+=cost or 0.0; pilot=chars.get(str(pid),{}).get('character_name','Active skills') if pid else 'Active skills'
            self.operation_manifest_tree.insert('', 'end', iid=str(idx), values=(shipname,qty,pilot,f'{maxr:.2f} LY','OK' if viable else 'NO',iso.replace(' Isotopes',''),f'{fuel:,}',self.format_isk(cost),f'{owned.get(iso,0):,}','…'))
        # Shortage is aggregate per isotope, then copied into each matching row for quick scanning.
        shortages={iso:max(0,required[iso]-owned.get(iso,0)) for iso in required}
        for iid in self.operation_manifest_tree.get_children():
            vals=list(self.operation_manifest_tree.item(iid,'values')); item=manifest[int(iid)] if int(iid)<len(manifest) else {}; shipname=normalize_ship_name(item.get('ship','Rhea')); iso=SHIPS.get(shipname,SHIPS['Rhea'])['isotope']; vals[-1]=f'{shortages.get(iso,0):,}'; self.operation_manifest_tree.item(iid,values=vals)
        chunks=[]
        for iso,n in required.items():
            if n:
                short=shortages[iso]; chunks.append(f'{iso}: {n:,} required / {owned.get(iso,0):,} owned / {short:,} short')
                if short:alerts.append(('WARN',op.get('name','Operation'),f'Fuel shortage: {short:,} {iso}', 'Before departure'))
        if not manifest:chunks=['Add ships to the manifest to calculate operation-wide fuel and shortages.']
        if manifest and total_cost:chunks.append(f'Jita replacement value: {self.format_isk(total_cost)} ISK')
        self.operation_fuel_summary.set('   •   '.join(chunks)); op['_fuel_alerts']=alerts

    def _refresh_operation_next(self,op,nodes):
        legs=op.get('legs',[]); idx=next((i for i,x in enumerate(legs) if str(x.get('status','PENDING'))!='DONE'),None)
        if idx is None or idx>=len(nodes)-1:self.operation_next_summary.set('OPERATION COMPLETE ✓');return
        a,b=nodes[idx],nodes[idx+1]; meta=legs[idx]; chars=self._sso_characters(); cid=int(meta.get('cyno_pilot_id',0) or 0); pilot=chars.get(str(cid),{}).get('character_name','unassigned') if cid else 'unassigned'; score=activity_score(self._activity_record(b[0]))
        self.operation_next_summary.set(f'NEXT JUMP  {a[1]}  →  {b[1]}   •   {distance_ly(a,b):.2f} LY   •   cyno {pilot}   •   activity {score}')

    def operation_add_current_ship(self):
        op=self._get_active_operation()
        if not op:messagebox.showinfo('Capital Operations','Create or load an operation first.',parent=self);return
        qty=max(1,int(self.operation_qty.get() or 1)); op.setdefault('manifest',[]).append({'ship':self.ship.get(),'qty':qty,'pilot_id':int(self.esi_character_id or 0)}); self._save_operations(); self.refresh_operation_ui()

    def operation_remove_manifest(self):
        op=self._get_active_operation(); sel=self.operation_manifest_tree.selection() if self.operation_manifest_tree else ()
        if not op or not sel:return
        try:idx=int(sel[0]); op['manifest'].pop(idx)
        except Exception:return
        self._save_operations(); self.refresh_operation_ui()

    def operation_assign_manifest_pilot(self):
        op=self._get_active_operation(); sel=self.operation_manifest_tree.selection() if self.operation_manifest_tree else ()
        if not op or not sel or not self.esi_character_id:return
        try:op['manifest'][int(sel[0])]['pilot_id']=int(self.esi_character_id)
        except Exception:return
        self._save_operations(); self.refresh_operation_ui()

    def _selected_operation_leg(self):
        if self.operation_route_tree is None or not self.operation_route_tree.selection():return None
        try:return int(self.operation_route_tree.selection()[0])
        except Exception:return None

    def operation_assign_active_pilot(self):
        op=self._get_active_operation(); idx=self._selected_operation_leg()
        if not op or idx is None:return
        if not self.esi_character_id:messagebox.showinfo('Cyno pilot','Select an active connected character first.',parent=self);return
        op['legs'][idx]['cyno_pilot_id']=int(self.esi_character_id); self._save_operations(); self.refresh_operation_ui()

    def operation_toggle_cyno_role(self):
        op=self._get_active_operation(); idx=self._selected_operation_leg()
        if not op or idx is None:return
        cur=str(op['legs'][idx].get('role','PRIMARY')); op['legs'][idx]['role']='BACKUP' if cur=='PRIMARY' else 'PRIMARY'; self._save_operations(); self.refresh_operation_ui()

    def operation_edit_note(self):
        op=self._get_active_operation(); idx=self._selected_operation_leg()
        if not op or idx is None:return
        old=str(op['legs'][idx].get('note','')); note=simpledialog.askstring('Leg note','Add a note for this cyno/jump leg:',initialvalue=old,parent=self)
        if note is None:return
        op['legs'][idx]['note']=note.strip(); self._save_operations(); self.refresh_operation_ui()

    def operation_mark_complete(self):
        op=self._get_active_operation()
        if not op:return
        idx=self._selected_operation_leg()
        if idx is None:idx=next((i for i,x in enumerate(op.get('legs',[])) if x.get('status')!='DONE'),None)
        if idx is None:return
        op['legs'][idx]['status']='DONE'; self._save_operations(); self.refresh_operation_ui()

    def operation_reset_legs(self):
        op=self._get_active_operation()
        if not op:return
        if not messagebox.askyesno('Reset operation','Reset every leg to PENDING?',parent=self):return
        for leg in op.get('legs',[]):leg['status']='PENDING'
        self._save_operations(); self.refresh_operation_ui()

    def operation_send_next(self):
        op=self._get_active_operation(); nodes=self._operation_route_nodes(op)
        if not op or len(nodes)<2:return
        idx=next((i for i,x in enumerate(op.get('legs',[])) if x.get('status')!='DONE'),None)
        if idx is None:return
        self.set_eve_destination(nodes[idx+1][1],int(self.esi_character_id or 0),append=False)

    def operation_send_selected_destination(self):
        op=self._get_active_operation(); nodes=self._operation_route_nodes(op); idx=self._selected_operation_leg()
        if idx is None or idx+1>=len(nodes):return
        self.set_eve_destination(nodes[idx+1][1])

    def refresh_activity_intel(self):
        if self.activity_refresh_running:return
        self.activity_refresh_running=True; self.activity_status.set('Refreshing last-hour system activity from CCP ESI…')
        def work():
            try:data=fetch_public_activity(); self.after(0,lambda:self._finish_activity_intel(data,None))
            except Exception as e:self.after(0,lambda msg=str(e):self._finish_activity_intel(None,msg))
        threading.Thread(target=work,daemon=True).start()

    def _finish_activity_intel(self,data,error):
        self.activity_refresh_running=False
        if error:self.activity_status.set('Activity refresh failed: '+error);return
        self.activity_data=data or {}; self.config['activity_cache']=self.activity_data; save_config(self.config)
        self.activity_status.set('Activity intel refreshed from CCP ESI • '+self._format_sync_time(self.activity_data.get('fetched_at'))); self.refresh_operation_ui()

    def operation_compare_routes(self):
        op=self._get_active_operation(); nodes=self._operation_route_nodes(op)
        if not op or len(nodes)<2:messagebox.showinfo('Route comparison','Create or load an operation first.',parent=self);return
        sh=SHIPS[self.ship.get()]; maxr=sh['range']*(1+0.2*self.jdc.get()); start,dest=nodes[0][1],nodes[-1][1]
        if self.operation_compare_tree is not None:self.operation_compare_tree.delete(*self.operation_compare_tree.get_children())
        self.operation_comparisons={}; variants=[('Fewest Jumps','Any systems'),('Fewest Jumps','Prefer NPC stations'),('Shortest Distance','Any systems'),('Shortest Distance','Prefer NPC stations'),('Fewest Jumps','NPC stations only')]
        for idx,(mode,policy) in enumerate(variants):
            a,b,path=route_path(start,dest,maxr,self.route_sec.get(),mode,[],[],sh,True,self.incursion_systems,self.use_live_rules.get(),policy)
            if not path:continue
            ds=[distance_ly(path[i],path[i+1]) for i in range(len(path)-1)]; fuel=sum(calc_fuel(d,sh,self.jfc.get(),self.ship_skill_level(sh)) for d in ds); cost=self.fuel_cost(sh['isotope'],fuel); stops=sum(1 for n in path[1:] if int(n[8] or 0)>0)
            iid=str(idx); self.operation_comparisons[iid]={'mode':mode,'policy':policy,'path':[n[1] for n in path]}; self.operation_compare_tree.insert('', 'end', iid=iid, values=(mode,policy,len(path)-1,f'{sum(ds):.2f}',stops,f'{fuel:,}',self.format_isk(cost)))
        self.operation_status.set(f'Compared {len(getattr(self,"operation_comparisons",{}))} viable route strategies for {self.ship.get()}.')

    def operation_use_comparison(self):
        if self.operation_compare_tree is None or not self.operation_compare_tree.selection():return
        comp=getattr(self,'operation_comparisons',{}).get(self.operation_compare_tree.selection()[0])
        if not comp:return
        self.route_mode.set(comp['mode']); self.route_station_policy.set(comp['policy']); self.route_from.set(comp['path'][0]); self.route_to.set(comp['path'][-1]); self.tabs.select(self.planner_tab); self.find_route()

    def show_station_details(self,system_name):
        node=system(system_name)
        if not node:return
        rows=stations_in_system(node[0]); win=tk.Toplevel(self); win.title(f'{node[1]} — NPC Stations'); win.geometry('820x420'); win.transient(self)
        outer=ttk.Frame(win,padding=12); outer.pack(fill='both',expand=True)
        ttk.Label(outer,text=f'{node[1]} — {node[7]}',style='SectionTitle.TLabel').pack(anchor='w'); ttk.Label(outer,text=f'Security {float(node[5]):.3f} • {len(rows)} NPC station(s) • station presence does not imply docking eligibility for every hull.',style='SectionSub.TLabel').pack(anchor='w',pady=(0,10))
        tree=ttk.Treeview(outer,columns=('id','owner','operation','type','name'),show='headings')
        for col,title,w in [('id','Station ID',95),('owner','Owner',210),('operation','Operation',180),('type','Type',160),('name','SDE name',200)]:tree.heading(col,text=title);tree.column(col,width=w,anchor='w')
        for r in rows:tree.insert('', 'end',values=(r[0],r[2] or '—',r[3] or '—',type_name(r[1]),r[4] or '—'))
        tree.pack(fill='both',expand=True); ttk.Button(outer,text='Close',command=win.destroy).pack(anchor='e',pady=(8,0))


    def update_ship_controls(self):
        sh=SHIPS.get(self.ship.get(),{})
        is_jf=bool(sh.get('jf_bonus'))
        self.jf_combo.configure(state='readonly' if is_jf else 'disabled')
        self.jf_label.configure(text='JUMP FREIGHTERS' if is_jf else 'JF SKILL // NOT USED')
        if hasattr(self,'dashboard_ship'): self.refresh_dashboard()

    def ship_skill_level(self,sh):
        return self.jf.get() if sh.get('jf_bonus') else 0

    def _market_cache_age(self):
        try:
            fetched=int(self.config.get('market_prices',{}).get('fetched_at',0) or 0)
        except (TypeError,ValueError):
            fetched=0
        return max(0,int(time.time())-fetched) if fetched else None

    def _market_time_text(self,epoch):
        try:
            return datetime.fromtimestamp(int(epoch)).astimezone().strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return 'unknown time'

    def _refresh_visible_costs(self):
        if self.range_origin.get().strip():
            try:self.find_range()
            except Exception:pass
        if self.route_from.get().strip() and self.route_to.get().strip():
            try:self.find_route()
            except Exception:pass
        if self.frm.get().strip() and self.to.get().strip():
            try:self.calculate()
            except Exception:pass

    def refresh_jita_prices(self,force=False):
        if self.market_refresh_running:
            self.price_status.set('Jita price refresh is already running…')
            return
        cache=self.config.get('market_prices',{}) if isinstance(self.config.get('market_prices',{}),dict) else {}
        age=self._market_cache_age()
        if not force and age is not None and age < MARKET_CACHE_SECONDS and cache.get('sell'):
            self.price_status.set(f'Using CCP ESI Jita 4-4 prices refreshed {age}s ago. Next automatic refresh is allowed after 5 minutes.')
            return
        self.market_refresh_running=True
        if self.price_refresh_btn is not None: self.price_refresh_btn.config(state='disabled')
        self.price_status.set('Contacting CCP ESI for current Jita 4-4 isotope prices…')
        def report(message,done,total):
            self.after(0,lambda m=message,d=done,t=total:self.price_status.set(f'{m} ({d}/{t})' if t else m))
        def work():
            try:
                data=fetch_jita_isotope_prices(report)
                self.after(0,lambda d=data:self._jita_prices_loaded(d))
            except Exception as e:
                self.after(0,lambda msg=str(e):self._jita_prices_failed(msg))
        threading.Thread(target=work,daemon=True).start()

    def _jita_prices_loaded(self,data):
        self.market_refresh_running=False
        if self.price_refresh_btn is not None: self.price_refresh_btn.config(state='normal')
        sell=data.get('sell',{}); buy=data.get('buy',{})
        for iso in ISOTOPE_TYPE_IDS:
            sp=sell.get(iso); bp=buy.get(iso)
            self.fuel_price_vars[iso].set('' if sp is None else f'{float(sp):.2f}')
            self.market_buy_vars[iso].set('—' if bp is None else f'{float(bp):.2f}')
        self.config['market_prices']=data
        # fuel_prices remains populated for backwards compatibility with older builds.
        self.config['fuel_prices']={k:float(v) for k,v in sell.items()}
        save_config(self.config)
        stamp=self._market_time_text(data.get('fetched_at'))
        self.price_status.set(f'Live CCP ESI prices loaded from Jita 4-4 at {stamp}. Best sell prices are now used for all fuel-cost calculations.')
        self._refresh_visible_costs()
        self.refresh_dashboard()

    def _jita_prices_failed(self,error):
        self.market_refresh_running=False
        if self.price_refresh_btn is not None: self.price_refresh_btn.config(state='normal')
        cache=self.config.get('market_prices',{}) if isinstance(self.config.get('market_prices',{}),dict) else {}
        if cache.get('sell'):
            stamp=self._market_time_text(cache.get('fetched_at'))
            self.price_status.set(f'Could not refresh CCP ESI ({error}). Using last Jita 4-4 prices from {stamp}.')
        else:
            self.price_status.set(f'Could not load Jita prices from CCP ESI: {error}. Fuel costs will show — until a price refresh succeeds.')

    def _clean_price_var(self,value):
        text=str(value).strip().replace(',','')
        if not text: return None
        try:
            price=float(text)
        except (TypeError,ValueError):
            return None
        return price if price >= 0 else None

    def fuel_price(self,isotope):
        var=self.fuel_price_vars.get(isotope)
        return self._clean_price_var(var.get()) if var is not None else None

    def fuel_cost(self,isotope,units):
        price=self.fuel_price(isotope)
        return None if price is None else float(units)*price

    def format_isk(self,value):
        if value is None: return '—'
        return f'{value:,.0f}'

    def save_fuel_prices(self):
        prices={}
        invalid=[]
        for iso,var in self.fuel_price_vars.items():
            raw=var.get().strip()
            if not raw: continue
            price=self._clean_price_var(raw)
            if price is None:
                invalid.append(iso); continue
            prices[iso]=price
            var.set(f'{price:g}')
        if invalid:
            messagebox.showwarning('Invalid fuel price','Enter a positive number or leave the field blank for: '+', '.join(invalid)); return
        self.config['fuel_prices']=prices; save_config(self.config)
        self.price_status.set('Fuel prices saved. Cost columns and totals now use these values.')
        # Refresh currently visible calculations where possible.
        if self.range_origin.get().strip():
            try:self.find_range()
            except Exception:pass
        if self.route_from.get().strip() and self.route_to.get().strip():
            try:self.find_route()
            except Exception:pass

    def clear_fuel_prices(self):
        for var in self.fuel_price_vars.values(): var.set('')
        self.config['fuel_prices']={}; save_config(self.config)
        self.price_status.set('Fuel prices cleared. Cost fields will show — until prices are entered again.')

    def _live_rules_cache_age(self):
        try: fetched=int(self.config.get('live_jump_restrictions',{}).get('fetched_at',0) or 0)
        except (TypeError,ValueError): fetched=0
        return max(0,int(time.time())-fetched) if fetched else None

    def refresh_live_jump_restrictions(self,force=False):
        if self.live_rules_running:
            self.live_rules_status.set('Live restrictions: refresh already running…'); return
        cache=self.config.get('live_jump_restrictions',{}) if isinstance(self.config.get('live_jump_restrictions',{}),dict) else {}
        age=self._live_rules_cache_age()
        if not force and age is not None and age<LIVE_RULES_CACHE_SECONDS:
            self.incursion_systems={int(x) for x in cache.get('incursion_systems',[]) if str(x).isdigit()}
            self.live_rules_status.set(f'Live restrictions: CCP ESI cache {age}s old • {len(self.incursion_systems)} Incursion-jammed systems.')
            return
        self.live_rules_running=True; self.live_rules_status.set('Live restrictions: checking CCP ESI Incursions…')
        def work():
            try:
                data=fetch_live_jump_restrictions()
                self.after(0,lambda d=data:self._live_jump_rules_loaded(d))
            except Exception as e:
                self.after(0,lambda msg=str(e):self._live_jump_rules_failed(msg))
        threading.Thread(target=work,daemon=True).start()

    def _live_jump_rules_loaded(self,data):
        self.live_rules_running=False
        self.incursion_systems={int(x) for x in data.get('incursion_systems',[]) if str(x).isdigit()}
        self.config['live_jump_restrictions']=data; save_config(self.config)
        stamp=self._market_time_text(data.get('fetched_at'))
        self.live_rules_status.set(f'Live restrictions: CCP ESI {stamp} • {len(self.incursion_systems)} Incursion-jammed systems.')
        if self.range_origin.get().strip():
            try:self.find_range()
            except Exception:pass
        if self.route_from.get().strip() and self.route_to.get().strip():
            try:self.find_route()
            except Exception:pass
        if self.frm.get().strip() and self.to.get().strip():
            try:self.calculate()
            except Exception:pass

    def _live_jump_rules_failed(self,error):
        self.live_rules_running=False
        cache=self.config.get('live_jump_restrictions',{}) if isinstance(self.config.get('live_jump_restrictions',{}),dict) else {}
        self.incursion_systems={int(x) for x in cache.get('incursion_systems',[]) if str(x).isdigit()}
        if cache.get('fetched_at'):
            self.live_rules_status.set(f'Live restrictions: ESI refresh failed; using cached Incursions ({len(self.incursion_systems)} systems).')
        else:
            self.live_rules_status.set(f'Live restrictions unavailable: {error}. Static legality still enforced.')

    def startup(self):
        migrate_windows_branding_shortcuts()
        m=load_meta(); self.status.set(f"SDE build: {m.get('sde_build','not installed')} • {m.get('system_count',0):,} systems • {int(m.get('npc_station_count',0) or 0):,} NPC stations • {int(m.get('stargate_connection_count',0) or 0):,} stargate links")
        if not database_schema_ready():
            self.write('EVE data needs the current resilient type-name + skill-prerequisite database.\n\nThe planner will now rebuild from the current official CCP Static Data Export. This rebuild imports item/ship/skill names from the CCP SDE and repairs any missing names from CCP ESI without blocking the navigation database.')
            self.do_update()
        self.refresh_jita_prices(force=False)
        self.refresh_asset_market_prices(force=False)
        self.refresh_live_jump_restrictions(force=False)
        self.restore_character_session()
        self.refresh_dashboard()
        self._skillplan_refresh_character_combo()
        if self.hunt_origin.get().strip() and self.hunting_data: self.after(900,self.scan_hunting_area)
        if self.active_operation_name in self.operations: self.refresh_operation_ui()
        if self.update_feed_url.get().strip(): self.after(1200,lambda:self.check_online_update(manual=False))
    def do_update(self):
        if self.update_running:
            self.show_update_dialog(); return
        self.update_running=True
        self.status.set('Checking CCP SDE…')
        self.update_btn.config(state='disabled')
        self.set_update_progress('Starting EVE data update…',0)
        self.show_update_dialog()
        def report(message,percent=None):
            self.after(0,lambda m=message,p=percent:self.set_update_progress(m,p))
        def completed(build,changed):
            self.status.set(f"SDE build {build} • {'updated' if changed else 'already current'}")
            self.write(f'EVE data ready. CCP SDE build {build}.\n\nYou can now enter two New Eden solar systems and calculate a jump.')
            self.update_btn.config(state='normal')
            self.finish_update_dialog('EVE data is up to date and ready.',True)
            self.refresh_dashboard(); self.refresh_command_center_views(force=True); self.refresh_operation_ui()
            if self.hunt_origin.get().strip():
                try:self.scan_hunting_area()
                except Exception:pass
        def failed(err):
            self.status.set('Update failed')
            self.update_btn.config(state='normal')
            # Keep the actual failure visible in the progress window.  Previous
            # builds replaced it with a generic message at 98%, which made a
            # recoverable validation problem look like an unexplained failure.
            detail='EVE data update failed: '+str(err)
            self.finish_update_dialog(detail,False)
            messagebox.showerror('Update failed',str(err),parent=self.update_window if self.update_window else self)
        def work():
            try:
                build,changed=update_sde(report)
                self.after(0,lambda b=build,c=changed:completed(b,c))
            except Exception as e:
                self.after(0,lambda msg=str(e):failed(msg))
        threading.Thread(target=work,daemon=True).start()
    def _safe_destroy(self):
        pending=getattr(self,'_responsive_after',None)
        if pending:
            try:self.after_cancel(pending)
            except Exception:pass
            self._responsive_after=None
        try:self.destroy()
        except tk.TclError:pass

    def on_close(self):
        self.config['app_state']={'ship':self.ship.get(),'jdc':self.jdc.get(),'jfc':self.jfc.get(),'jf':self.jf.get(),'range_station_filter':self.range_station_filter.get(),'route_station_policy':self.route_station_policy.get(),'route_require_dest_station':bool(self.route_require_dest_station.get()),'hunt_origin':self.hunt_origin.get().strip(),'hunt_max_hops':int(self.hunt_max_hops.get() or 10),'hunt_security':self.hunt_security.get(),'hunt_mode':self.hunt_mode.get(),'hunt_min_npc':int(self.hunt_min_npc.get() or 0)}
        self.config['fuel_prices']={iso:self._clean_price_var(var.get()) for iso,var in self.fuel_price_vars.items() if self._clean_price_var(var.get()) is not None}
        self.config['update_feed_url']=self.update_feed_url.get().strip()
        self.config['favorite_systems']=list(self.favorite_systems)
        self.config['recent_routes']=list(self.recent_routes[:20])
        self.config['operations']=self.operations
        self.config['active_operation']=self.active_operation_name
        self.config['activity_cache']=self.activity_data
        self.config['hunting_cache']=self.hunting_data
        self.config['ess_observations']=self.ess_observations
        sso=self.config.setdefault('esi_sso',{})
        sso['auto_apply']=bool(self.esi_auto_apply.get())
        sso['active_character_id']=int(self.esi_character_id or 0)
        try: save_config(self.config)
        except Exception: pass
        self._safe_destroy()

    def _sso_characters(self):
        sso=self.config.setdefault('esi_sso',{})
        chars=sso.get('characters')
        if not isinstance(chars,dict):
            chars={}; sso['characters']=chars
        return chars

    def _selected_character_id(self):
        if self.esi_character_tree is not None:
            sel=self.esi_character_tree.selection()
            if sel:
                try:return int(sel[0])
                except Exception:pass
        return int(self.esi_character_id or 0)

    def _format_sync_time(self,value):
        if not value:return 'Never'
        try:
            if isinstance(value,(int,float)) or (isinstance(value,str) and value.isdigit()):
                dt=datetime.fromtimestamp(float(value),tz=timezone.utc)
            else:
                dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
                if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime('%Y-%m-%d %H:%M')
        except Exception:return str(value)

    def _refresh_character_tree(self,select_id=None):
        if self.esi_character_tree is None:return
        chars=self._sso_characters(); selected=int(select_id or 0)
        current=self.esi_character_tree.selection()
        if not selected and current:
            try:selected=int(current[0])
            except Exception:pass
        self.esi_character_tree.delete(*self.esi_character_tree.get_children())
        for key,rec in sorted(chars.items(),key=lambda kv:str(kv[1].get('character_name','')).casefold()):
            try:cid=int(rec.get('character_id') or key)
            except Exception:continue
            skills=rec.get('skills',{}) if isinstance(rec.get('skills',{}),dict) else {}
            scopes=set(rec.get('scopes',[]) if isinstance(rec.get('scopes',[]),list) else [])
            vals=(
                '✓' if cid==int(self.esi_character_id or 0) else '',
                str(rec.get('character_name') or f'Character {cid}'),
                skills.get('Jump Drive Calibration','—'),
                skills.get('Jump Fuel Conservation','—'),
                skills.get('Jump Freighters','—'),
                'Ready' if ESI_WAYPOINT_SCOPE in scopes else 'Reconnect',
                'Ready' if set(ESI_REQUESTED_SCOPES).issubset(scopes) else 'Reconnect',
                self._format_sync_time(rec.get('last_sync_utc')),
            )
            self.esi_character_tree.insert('', 'end', iid=str(cid), values=vals)
        if selected and self.esi_character_tree.exists(str(selected)):
            self.esi_character_tree.selection_set(str(selected)); self.esi_character_tree.see(str(selected))
        elif self.esi_character_id and self.esi_character_tree.exists(str(self.esi_character_id)):
            self.esi_character_tree.selection_set(str(self.esi_character_id)); self.esi_character_tree.see(str(self.esi_character_id))
        elif self.esi_character_tree.get_children():
            first=self.esi_character_tree.get_children()[0]; self.esi_character_tree.selection_set(first)
        self._character_selection_changed()

    def _character_selection_changed(self):
        cid=self._selected_character_id(); chars=self._sso_characters(); rec=chars.get(str(cid),{}) if cid else {}
        if rec:
            name=str(rec.get('character_name') or f'Character {cid}')
            self.esi_character_name.set(name)
            skills=rec.get('skills',{}) if isinstance(rec.get('skills',{}),dict) else {}
            for skill,var in self.esi_skill_vars.items():var.set(str(skills.get(skill,'—')))
            self.esi_skills_status.set(f"JDC {skills.get('Jump Drive Calibration','—')} • JFC {skills.get('Jump Fuel Conservation','—')} • Jump Freighters {skills.get('Jump Freighters','—')} • synced {self._format_sync_time(rec.get('last_sync_utc'))}")
            active=' • currently used by planner' if cid==int(self.esi_character_id or 0) else ''
            scopes=set(rec.get('scopes',[]) if isinstance(rec.get('scopes',[]),list) else [])
            route_state=' • in-game destination READY' if ESI_WAYPOINT_SCOPE in scopes else ' • re-authorize to enable in-game destination'
            companion_state=' • command data READY' if set(ESI_REQUESTED_SCOPES).issubset(scopes) else ' • re-authorize for full Command Center data'
            self.esi_character_status.set(f'{name} is connected through CCP EVE SSO{active}{route_state}{companion_state}.')
        else:
            self.esi_character_name.set('No character selected')
            for var in self.esi_skill_vars.values():var.set('—')
            self.esi_skills_status.set('Select a character to view and apply its jump skills.')
            self.esi_character_status.set('Add an EVE character or select one already connected on this PC.')
        state='normal' if rec and not self.esi_sso_running else 'disabled'
        if self.esi_refresh_btn is not None:self.esi_refresh_btn.config(state=state)
        if self.esi_use_btn is not None:self.esi_use_btn.config(state=state)
        if self.esi_remove_btn is not None:self.esi_remove_btn.config(state=state)
        if self.esi_refresh_all_btn is not None:self.esi_refresh_all_btn.config(state='normal' if chars and not self.esi_sso_running else 'disabled')

    def _set_character_busy(self,busy,message=None):
        self.esi_sso_running=busy
        if self.esi_connect_btn is not None:self.esi_connect_btn.config(state='disabled' if busy or not APP_SSO_CLIENT_ID else 'normal')
        if self.esi_refresh_btn is not None:self.esi_refresh_btn.config(state='disabled' if busy else 'normal')
        if self.esi_refresh_all_btn is not None:self.esi_refresh_all_btn.config(state='disabled' if busy else ('normal' if self._sso_characters() else 'disabled'))
        if self.esi_use_btn is not None:self.esi_use_btn.config(state='disabled' if busy else 'normal')
        if self.esi_remove_btn is not None:self.esi_remove_btn.config(state='disabled' if busy else 'normal')
        if message:self.esi_character_status.set(message)
        if not busy:self._character_selection_changed()

    def _persist_character_connection(self,verify,skills,refresh_token=None,make_active=True):
        cid=int(verify.get('CharacterID') or verify.get('character_id') or 0)
        name=str(verify.get('CharacterName') or verify.get('character_name') or '').strip() or (f'Character {cid}' if cid else 'EVE character')
        if not cid:raise RuntimeError('EVE SSO did not return a character ID.')
        levels=skill_levels_from_esi(skills)
        chars=self._sso_characters(); existing=chars.get(str(cid),{}) if isinstance(chars.get(str(cid),{}),dict) else {}
        raw_scopes=verify.get('Scopes') or verify.get('scopes') or existing.get('scopes',[]) or []
        if isinstance(raw_scopes,str): raw_scopes=raw_scopes.split()
        scopes=sorted({str(x) for x in raw_scopes if str(x).strip()})
        rec={
            'character_id':cid,
            'character_name':name,
            'skills':levels,
            'scopes':scopes,
            'last_sync_utc':datetime.now(timezone.utc).isoformat(),
            'refresh_token_dpapi':str(existing.get('refresh_token_dpapi','')),
        }
        if refresh_token:
            protected=protect_refresh_token(refresh_token)
            if protected:rec['refresh_token_dpapi']=protected
        chars[str(cid)]=rec
        if make_active:
            self.esi_character_id=cid
            self.config.setdefault('esi_sso',{})['active_character_id']=cid
        self.config.setdefault('esi_sso',{})['auto_apply']=bool(self.esi_auto_apply.get())
        save_config(self.config)
        self._refresh_character_tree(cid)
        self.esi_character_status.set(f'Connected to {name}. You can add more characters with Add character.')
        if make_active and self.esi_auto_apply.get():self.apply_character_skills(silent=True)
        self._set_character_busy(False)

    def connect_eve_character(self):
        if self.esi_sso_running:return
        client_id=APP_SSO_CLIENT_ID; redirect=APP_SSO_REDIRECT_URI
        if not client_id:
            messagebox.showerror('EVE SSO not configured','This development build has no embedded CCP EVE SSO Client ID. Rebuild the release after configuring developer_settings.local.json.',parent=self); return
        try:parsed=validate_loopback_redirect(redirect)
        except Exception as e:
            messagebox.showerror('Invalid embedded callback URL',str(e),parent=self); return
        self._set_character_busy(True,'Preparing secure CCP EVE SSO login…')
        def work():
            server=None
            try:
                metadata=fetch_sso_metadata()
                verifier=_b64url(secrets.token_bytes(32)); challenge=_b64url(hashlib.sha256(verifier.encode('ascii')).digest()); state=_b64url(secrets.token_bytes(24))
                result={}; expected_path=parsed.path or '/'
                class Handler(http.server.BaseHTTPRequestHandler):
                    def do_GET(hself):
                        q=urllib.parse.urlparse(hself.path)
                        if q.path!=expected_path:
                            hself.send_response(404); hself.end_headers(); return
                        result.update({k:v[-1] for k,v in urllib.parse.parse_qs(q.query).items() if v})
                        body=b'<!doctype html><meta charset="utf-8"><title>New Eden Command</title><style>body{font-family:Segoe UI,Arial,sans-serif;max-width:650px;margin:80px auto;padding:24px}h1{font-size:24px}</style><h1>New Eden Command</h1><p>Character login received. You can close this browser tab and return to the planner.</p>'
                        hself.send_response(200); hself.send_header('Content-Type','text/html; charset=utf-8'); hself.send_header('Content-Length',str(len(body))); hself.end_headers(); hself.wfile.write(body)
                    def log_message(hself,fmt,*args):pass
                server=http.server.HTTPServer(('127.0.0.1',parsed.port),Handler); server.timeout=180
                params={'response_type':'code','client_id':client_id,'redirect_uri':redirect,'scope':ESI_SCOPE_STRING,'state':state,'code_challenge':challenge,'code_challenge_method':'S256'}
                auth_url=metadata['authorization_endpoint']+'?'+urllib.parse.urlencode(params)
                self.after(0,lambda:self.esi_character_status.set('Browser opened for CCP EVE login. Choose the character you want to add.'))
                webbrowser.open(auth_url,new=2); server.handle_request()
                if not result:raise RuntimeError('EVE login timed out after 3 minutes. Try Add character again.')
                if result.get('error'):raise RuntimeError('EVE SSO login was not completed: '+result.get('error_description',result['error']))
                if result.get('state')!=state:raise RuntimeError('EVE SSO state check failed; the login response was rejected.')
                code=result.get('code')
                if not code:raise RuntimeError('EVE SSO did not return an authorization code.')
                tokens=exchange_sso_code(client_id,redirect,code,verifier,metadata['token_endpoint'])
                access=tokens.get('access_token'); refresh=tokens.get('refresh_token')
                if not access:raise RuntimeError('EVE SSO did not return an access token.')
                verify=verify_sso_access(access)
                scopes=verify.get('Scopes') or verify.get('scopes') or []
                if isinstance(scopes,str):scopes=scopes.split()
                if scopes and ESI_SKILLS_SCOPE not in scopes:raise RuntimeError('The connected character did not grant the required skills scope.')
                cid=int(verify.get('CharacterID') or verify.get('character_id') or 0)
                skills=fetch_character_skills(cid,access)
                self.after(0,lambda v=verify,sk=skills,rt=refresh:self._persist_character_connection(v,sk,rt,True))
            except Exception as e:
                self.after(0,lambda msg=str(e):self._character_login_failed(msg))
            finally:
                try:
                    if server:server.server_close()
                except Exception:pass
        threading.Thread(target=work,daemon=True).start()

    def _character_login_failed(self,error):
        self._set_character_busy(False,f'EVE character operation failed: {error}')
        messagebox.showerror('EVE character login',error,parent=self)

    def _fetch_refreshed_character(self,character_id):
        chars=self._sso_characters(); rec=chars.get(str(int(character_id)),{})
        if not rec:raise RuntimeError('The selected character is not saved on this PC.')
        protected=str(rec.get('refresh_token_dpapi',''))
        refresh=unprotect_refresh_token(protected) if protected else ''
        if not refresh:raise RuntimeError(f"No protected refresh token is available for {rec.get('character_name','this character')}. Add that character again.")
        if not APP_SSO_CLIENT_ID:raise RuntimeError('This build has no embedded CCP EVE SSO Client ID.')
        metadata=fetch_sso_metadata(); tokens=refresh_sso_access(APP_SSO_CLIENT_ID,refresh,metadata['token_endpoint'])
        access=tokens.get('access_token'); rotated=tokens.get('refresh_token') or refresh
        if not access:raise RuntimeError('EVE SSO refresh did not return an access token.')
        verify=verify_sso_access(access); cid=int(verify.get('CharacterID') or verify.get('character_id') or 0)
        if cid!=int(character_id):raise RuntimeError('The refreshed EVE token returned a different character and was rejected.')
        skills=fetch_character_skills(cid,access)
        return verify,skills,rotated

    def refresh_character_skills(self):
        if self.esi_sso_running:return
        cid=self._selected_character_id()
        if not cid:
            messagebox.showinfo('EVE character','Select a character first.',parent=self); return
        self._set_character_busy(True,'Refreshing selected character skills from CCP ESI…')
        def work():
            try:
                result=self._fetch_refreshed_character(cid)
                self.after(0,lambda r=result:self._persist_character_connection(r[0],r[1],r[2],cid==int(self.esi_character_id or 0)))
            except Exception as e:self.after(0,lambda msg=str(e):self._character_login_failed(msg))
        threading.Thread(target=work,daemon=True).start()

    def refresh_all_character_skills(self):
        if self.esi_sso_running:return
        ids=[]
        for key in self._sso_characters():
            try:ids.append(int(key))
            except Exception:pass
        if not ids:return
        self._set_character_busy(True,f'Refreshing {len(ids)} EVE characters from CCP ESI…')
        active=int(self.esi_character_id or 0)
        def work():
            successes=[]; errors=[]
            for cid in ids:
                try:successes.append((cid,self._fetch_refreshed_character(cid)))
                except Exception as e:errors.append((cid,str(e)))
            self.after(0,lambda:self._finish_refresh_all(successes,errors,active))
        threading.Thread(target=work,daemon=True).start()

    def _finish_refresh_all(self,successes,errors,active):
        for cid,(verify,skills,token) in successes:
            # Inline persistence keeps a batch refresh from toggling busy state per row.
            levels=skill_levels_from_esi(skills); chars=self._sso_characters(); old=chars.get(str(cid),{})
            name=str(verify.get('CharacterName') or verify.get('character_name') or old.get('character_name') or f'Character {cid}')
            protected=protect_refresh_token(token) if token else str(old.get('refresh_token_dpapi',''))
            raw_scopes=verify.get('Scopes') or verify.get('scopes') or old.get('scopes',[]) or []
            if isinstance(raw_scopes,str): raw_scopes=raw_scopes.split()
            chars[str(cid)]={'character_id':cid,'character_name':name,'skills':levels,'scopes':sorted({str(x) for x in raw_scopes if str(x).strip()}),'last_sync_utc':datetime.now(timezone.utc).isoformat(),'refresh_token_dpapi':protected or str(old.get('refresh_token_dpapi',''))}
        self.config.setdefault('esi_sso',{})['active_character_id']=active
        save_config(self.config); self._refresh_character_tree(active)
        self._set_character_busy(False)
        if active and active in [cid for cid,_ in successes] and self.esi_auto_apply.get():
            self.use_character(active,apply=True)
        if errors:
            names=[]; chars=self._sso_characters()
            for cid,msg in errors:names.append(f"{chars.get(str(cid),{}).get('character_name',cid)}: {msg}")
            messagebox.showwarning('Character refresh',f'Refreshed {len(successes)} character(s).\n\nCould not refresh:\n'+'\n'.join(names),parent=self)
        else:self.esi_character_status.set(f'Refreshed all {len(successes)} connected characters.')

    def restore_character_session(self):
        chars=self._sso_characters()
        active=int(self.config.get('esi_sso',{}).get('active_character_id',0) or 0)
        if active and str(active) not in chars:active=0
        if not active and chars:
            try:active=int(next(iter(chars)))
            except Exception:active=0
        self.esi_character_id=active
        self._refresh_character_tree(active)
        if not APP_SSO_CLIENT_ID:
            self.esi_character_status.set('EVE SSO is not configured in this development build. Existing cached skills remain usable.'); return
        if not active:return
        rec=chars.get(str(active),{})
        if not rec.get('refresh_token_dpapi'):return
        self._set_character_busy(True,f"Refreshing {rec.get('character_name','saved character')} skills…")
        def work():
            try:
                result=self._fetch_refreshed_character(active)
                self.after(0,lambda r=result:self._persist_character_connection(r[0],r[1],r[2],True))
            except Exception as e:self.after(0,lambda msg=str(e):self._restore_character_failed(msg))
        threading.Thread(target=work,daemon=True).start()

    def _restore_character_failed(self,error):
        self._set_character_busy(False,f'Could not refresh the active EVE character: {error}. Cached skills remain available.')

    def use_character(self,cid,apply=None):
        chars=self._sso_characters(); rec=chars.get(str(int(cid)),{})
        if not rec:return
        self.esi_character_id=int(cid); self.config.setdefault('esi_sso',{})['active_character_id']=int(cid); save_config(self.config)
        self._refresh_character_tree(int(cid)); self._character_selection_changed()
        if apply is None:apply=bool(self.esi_auto_apply.get())
        if apply:self.apply_character_skills(silent=True)
        self.esi_character_status.set(f"Using {rec.get('character_name',f'Character {cid}')} for planner skills.")
        self.refresh_dashboard()

    def use_selected_character(self):
        cid=self._selected_character_id()
        if cid:self.use_character(cid,apply=True)

    def apply_character_skills(self,silent=False):
        cid=self._selected_character_id()
        rec=self._sso_characters().get(str(cid),{}) if cid else {}
        skills=rec.get('skills',{}) if isinstance(rec.get('skills',{}),dict) else {}
        try:
            jdc=int(skills.get('Jump Drive Calibration')); jfc=int(skills.get('Jump Fuel Conservation')); jf=int(skills.get('Jump Freighters'))
        except Exception:
            if not silent:messagebox.showinfo('Character skills','Select a character with synced skills first.',parent=self)
            return
        self.jdc.set(jdc); self.jfc.set(jfc); self.jf.set(jf); self.update_ship_controls()
        self.esi_character_id=cid; self.config.setdefault('esi_sso',{})['active_character_id']=cid; save_config(self.config)
        if not silent:self.esi_skills_status.set(f'Applied to planner: JDC {jdc} • JFC {jfc} • Jump Freighters {jf}.')
        self._refresh_character_tree(cid); self._refresh_visible_costs()

    def remove_eve_character(self):
        if self.esi_sso_running:
            messagebox.showinfo('EVE character','Wait for the current SSO operation to finish.',parent=self); return
        cid=self._selected_character_id(); chars=self._sso_characters(); rec=chars.get(str(cid),{}) if cid else {}
        if not rec:return
        name=str(rec.get('character_name') or f'Character {cid}')
        if not messagebox.askyesno('Remove EVE character',f'Remove {name} from this PC?\n\nThis deletes its locally protected refresh token. You can add the character again later.',parent=self):return
        chars.pop(str(cid),None)
        if cid==int(self.esi_character_id or 0):
            self.esi_character_id=0
            if chars:
                try:self.esi_character_id=int(next(iter(chars)))
                except Exception:pass
        self.config.setdefault('esi_sso',{})['active_character_id']=int(self.esi_character_id or 0); save_config(self.config)
        self._refresh_character_tree(self.esi_character_id)
        if self.esi_character_id and self.esi_auto_apply.get():self.use_character(self.esi_character_id,apply=True)

    def bind_system_entry_context(self,entry,var):
        """Give every system input the same right-click actions as result tables."""
        entry.bind('<Button-3>',lambda event,v=var:self.system_entry_context_menu(event,v),add='+')

    def system_entry_context_menu(self,event,var):
        name=str(var.get()).strip()
        if system(name): self.show_system_context_menu(event,name)

    def range_tree_context_menu(self,event):
        row=self.tree.identify_row(event.y)
        if not row:return
        self.tree.selection_set(row); self.tree.focus(row)
        vals=self.tree.item(row,'values')
        if vals:self.show_system_context_menu(event,str(vals[0]))

    def route_tree_context_menu(self,event):
        row=self.route_tree.identify_row(event.y)
        if not row:return
        self.route_tree.selection_set(row); self.route_tree.focus(row)
        vals=self.route_tree.item(row,'values')
        if len(vals)>=3:self.show_system_context_menu(event,str(vals[2]))

    def route_map_context_menu(self,event):
        if not self.route_map_hitboxes:return
        best=None
        for x,y,r,i in self.route_map_hitboxes:
            d=(event.x-x)**2+(event.y-y)**2
            if d<=max(r,18)**2 and (best is None or d<best[0]):best=(d,i)
        if best is None:return
        self.route_map_selected_index=best[1]
        self.redraw_route_map()
        node=self.last_route_nodes[self.route_map_selected_index]
        self.show_system_context_menu(event,str(node[1]))

    def _active_character_label(self):
        cid=int(self.esi_character_id or 0)
        rec=self._sso_characters().get(str(cid),{}) if cid else {}
        return str(rec.get('character_name') or 'active character')

    def _copy_text(self,value):
        try:
            self.clipboard_clear(); self.clipboard_append(str(value)); self.update_idletasks()
            self.status.set(f'Copied {value} to clipboard.')
        except Exception:pass

    def _set_system_as_route_destination(self,name):
        if not system(name):return
        self.route_to.set(name); self.tabs.select(self.planner_tab)
        self.status.set(f'{name} set as Route Planner destination.')

    def _set_system_as_jump_destination(self,name):
        if not system(name):return
        self.to.set(name); self.tabs.select(self.jump_tab)
        self.status.set(f'{name} set as Jump Calculator destination.')

    def _set_system_as_range_origin(self,name):
        if not system(name):return
        self.range_origin.set(name); self.tabs.select(self.range_tab); self.find_range()

    def show_system_context_menu(self,event,system_name):
        node=system(system_name)
        if not node:return
        name=str(node[1]); region=str(node[7]); cid=int(self.esi_character_id or 0)
        chars=self._sso_characters()
        rec=chars.get(str(cid),{}) if cid else {}
        scopes=set(rec.get('scopes',[]) if isinstance(rec.get('scopes',[]),list) else [])
        ready=bool(cid and ESI_WAYPOINT_SCOPE in scopes)
        menu=tk.Menu(self,tearoff=0,bg='#0d151e',fg='#e5edf3',activebackground='#164b68',activeforeground='#ffffff',bd=1,relief='solid')
        active_name=str(rec.get('character_name') or 'No active character')
        menu.add_command(label=f'Set destination in EVE — {active_name}',state='normal' if ready else 'disabled',command=lambda:self.set_eve_destination(name,cid,append=False))
        menu.add_command(label=f'Add waypoint in EVE — {active_name}',state='normal' if ready else 'disabled',command=lambda:self.set_eve_destination(name,cid,append=True))
        if len(chars)>1:
            sub=tk.Menu(menu,tearoff=0,bg='#0d151e',fg='#e5edf3',activebackground='#164b68',activeforeground='#ffffff')
            for key,item in sorted(chars.items(),key=lambda kv:str(kv[1].get('character_name','')).casefold()):
                try:char_id=int(item.get('character_id') or key)
                except Exception:continue
                char_scopes=set(item.get('scopes',[]) if isinstance(item.get('scopes',[]),list) else [])
                label=str(item.get('character_name') or f'Character {char_id}')
                if ESI_WAYPOINT_SCOPE not in char_scopes:label+=' — reconnect required'
                sub.add_command(label=label,state='normal' if ESI_WAYPOINT_SCOPE in char_scopes else 'disabled',command=lambda c=char_id:self.set_eve_destination(name,c,append=False))
            menu.add_cascade(label='Set destination for character…',menu=sub)
        if not ready:
            menu.add_command(label='Enable in-game destination…',command=lambda:self._open_character_for_permissions())
        menu.add_separator()
        pinned=any(x.casefold()==name.casefold() for x in self.favorite_systems)
        menu.add_command(label=('Unpin from Flight Deck' if pinned else 'Pin to Flight Deck'),command=lambda:self.toggle_favorite_system(name))
        menu.add_command(label='Use as Systems in Range origin',command=lambda:self._set_system_as_range_origin(name))
        menu.add_command(label='Set as Route Planner destination',command=lambda:self._set_system_as_route_destination(name))
        menu.add_command(label='Set as Jump Calculator destination',command=lambda:self._set_system_as_jump_destination(name))
        if len(node)>8 and int(node[8] or 0)>0:
            menu.add_command(label=f'Show NPC stations ({int(node[8])})',command=lambda:self.show_station_details(name))
        menu.add_separator()
        menu.add_command(label=f'Copy {name}',command=lambda:self._copy_text(name))
        activity=self._activity_record(node[0]) if hasattr(self,'activity_data') else {}
        if activity:
            menu.add_command(label=f"Last-hour activity: score {activity_score(activity)} • {int(activity.get('ship_kills',0) or 0)} ship kills • {int(activity.get('pod_kills',0) or 0)} pod kills • {int(activity.get('ship_jumps',0) or 0)} jumps",state='disabled')
        menu.add_command(label=f'{region}  •  security {float(node[5]):.3f}  •  NPC stations {int(node[8] or 0) if len(node)>8 else 0}',state='disabled')
        try:menu.tk_popup(event.x_root,event.y_root)
        finally:
            try:menu.grab_release()
            except Exception:pass

    def _open_character_for_permissions(self):
        self.tabs.select(self.character_tab)
        self.esi_character_status.set('To enable Set destination in EVE, click Add character / re-authorize and approve the in-game waypoint permission for that character.')

    def _access_token_for_character(self,character_id,required_scope=None):
        """Refresh one character and return a short-lived access token.

        Refresh-token rotation is persisted immediately.  Scope upgrades cannot be
        obtained by refresh, so an older character must be re-authorized if the
        waypoint scope was not granted when it was added.
        """
        cid=int(character_id or 0); chars=self._sso_characters(); rec=chars.get(str(cid),{})
        if not rec:raise RuntimeError('That EVE character is not connected on this PC.')
        protected=str(rec.get('refresh_token_dpapi',''))
        refresh=unprotect_refresh_token(protected) if protected else ''
        if not refresh:raise RuntimeError(f"No protected refresh token is available for {rec.get('character_name','this character')}. Add the character again.")
        if not APP_SSO_CLIENT_ID:raise RuntimeError('This build has no embedded CCP EVE SSO Client ID.')
        metadata=fetch_sso_metadata(); tokens=refresh_sso_access(APP_SSO_CLIENT_ID,refresh,metadata['token_endpoint'])
        access=tokens.get('access_token'); rotated=tokens.get('refresh_token') or refresh
        if not access:raise RuntimeError('EVE SSO refresh did not return an access token.')
        verify=verify_sso_access(access); returned=int(verify.get('CharacterID') or verify.get('character_id') or 0)
        if returned!=cid:raise RuntimeError('The refreshed EVE token returned a different character and was rejected.')
        raw_scopes=verify.get('Scopes') or verify.get('scopes') or []
        if isinstance(raw_scopes,str):raw_scopes=raw_scopes.split()
        scopes=sorted({str(x) for x in raw_scopes if str(x).strip()})
        if required_scope and required_scope not in scopes:
            raise RuntimeError(f"{rec.get('character_name','This character')} has not granted {required_scope}. Open the Character tab and use Add character / re-authorize, then select the same character.")
        protected_rotated=protect_refresh_token(rotated) if rotated else ''
        if protected_rotated:rec['refresh_token_dpapi']=protected_rotated
        rec['scopes']=scopes
        rec['character_name']=str(verify.get('CharacterName') or verify.get('character_name') or rec.get('character_name') or f'Character {cid}')
        chars[str(cid)]=rec; save_config(self.config)
        return access,rec

    def set_eve_destination(self,system_name,character_id=None,append=False):
        """Set or append an in-game autopilot waypoint via CCP ESI."""
        name=str(system_name or '').strip(); node=system(name)
        if not node:
            messagebox.showinfo('Set destination in EVE','Choose a valid solar system first.',parent=self); return
        cid=int(character_id or self.esi_character_id or 0)
        if not cid:
            messagebox.showinfo('Set destination in EVE','Add an EVE character on the Character tab first.',parent=self); self.tabs.select(self.character_tab); return
        rec=self._sso_characters().get(str(cid),{})
        scopes=set(rec.get('scopes',[]) if isinstance(rec.get('scopes',[]),list) else [])
        if ESI_WAYPOINT_SCOPE not in scopes:
            messagebox.showinfo('Permission required',f"{rec.get('character_name','This character')} needs the in-game waypoint permission.\n\nOpen Character and use Add character / re-authorize, selecting the same character.",parent=self)
            self._open_character_for_permissions(); return
        if self.in_game_action_running:
            self.status.set('An in-game waypoint action is already running.'); return
        char_name=str(rec.get('character_name') or f'Character {cid}')
        action='Adding waypoint' if append else 'Setting destination'
        self.in_game_action_running=True; self.status.set(f'{action}: {name} → {char_name}…')
        def work():
            try:
                access,fresh=self._access_token_for_character(cid,ESI_WAYPOINT_SCOPE)
                post_autopilot_waypoint(int(node[0]),access,clear_other_waypoints=not append,add_to_beginning=False)
                self.after(0,lambda:self._finish_eve_waypoint(name,str(fresh.get('character_name') or char_name),append,None))
            except Exception as e:self.after(0,lambda msg=str(e):self._finish_eve_waypoint(name,char_name,append,msg))
        threading.Thread(target=work,daemon=True).start()

    def _finish_eve_waypoint(self,name,char_name,append,error):
        self.in_game_action_running=False; self._refresh_character_tree(self.esi_character_id)
        if error:
            self.status.set(f'Could not send {name} to EVE.')
            messagebox.showerror('EVE in-game destination',error,parent=self); return
        verb='Added waypoint' if append else 'Destination set'
        self.status.set(f'{verb} in EVE for {char_name}: {name}.')

    def send_route_to_eve(self):
        """Send the calculated jump-chain systems as EVE autopilot waypoints."""
        if len(self.last_route_nodes)<2:
            messagebox.showinfo('Send route to EVE','Calculate a route first.',parent=self); return
        cid=int(self.esi_character_id or 0); rec=self._sso_characters().get(str(cid),{}) if cid else {}
        scopes=set(rec.get('scopes',[]) if isinstance(rec.get('scopes',[]),list) else [])
        if not cid or ESI_WAYPOINT_SCOPE not in scopes:
            messagebox.showinfo('Permission required','Select a connected character with In-game route = Ready. Re-authorize the character if needed.',parent=self); self.tabs.select(self.character_tab); return
        nodes=list(self.last_route_nodes[1:])
        if len(nodes)>60:
            messagebox.showwarning('Route too long','For safety, sending a route is limited to 60 waypoint systems.',parent=self); return
        if self.in_game_action_running:return
        char_name=str(rec.get('character_name') or f'Character {cid}')
        self.in_game_action_running=True; self.status.set(f'Sending {len(nodes)} route waypoint(s) to EVE for {char_name}…')
        def work():
            try:
                access,fresh=self._access_token_for_character(cid,ESI_WAYPOINT_SCOPE)
                for i,node in enumerate(nodes):
                    post_autopilot_waypoint(int(node[0]),access,clear_other_waypoints=(i==0),add_to_beginning=False)
                    self.after(0,lambda done=i+1,total=len(nodes):self.status.set(f'Sending route to EVE… {done}/{total} waypoint(s)'))
                self.after(0,lambda:self._finish_send_route(str(fresh.get('character_name') or char_name),len(nodes),None))
            except Exception as e:self.after(0,lambda msg=str(e):self._finish_send_route(char_name,len(nodes),msg))
        threading.Thread(target=work,daemon=True).start()

    def _finish_send_route(self,char_name,count,error):
        self.in_game_action_running=False; self._refresh_character_tree(self.esi_character_id)
        if error:
            self.status.set('Could not send route waypoints to EVE.'); messagebox.showerror('Send route to EVE',error,parent=self); return
        self.status.set(f'Sent {count} jump-chain system(s) to EVE as autopilot waypoints for {char_name}.')

    def save_update_feed(self):
        raw=self.update_feed_url.get().strip()
        if raw:
            try:_validate_update_feed_url(raw)
            except Exception as e:
                messagebox.showerror('Invalid update feed',str(e),parent=self); return
        self.config['update_feed_url']=raw
        save_config(self.config)
        self.app_update_status.set('Update feed saved.' if raw else 'Online update feed cleared. Local .ejpupdate files can still be installed.')

    def _set_online_progress(self,message,done=0,total=0):
        self.app_update_status.set(message)
        pct=0.0
        if total:
            pct=max(0.0,min(100.0,float(done)*100.0/float(total)))
        self.app_update_progress.set(pct)
        if total and total>=1024*1024:
            self.app_update_percent.set(f'{pct:.0f}%  {done/1048576:.1f}/{total/1048576:.1f} MB')
        elif total:
            self.app_update_percent.set(f'{pct:.0f}%')
        else:
            self.app_update_percent.set('')

    def check_online_update(self,manual=True):
        if self.online_check_running or self.online_download_running: return
        url=self.update_feed_url.get().strip()
        if not url:
            if manual: messagebox.showinfo('Online updates','Enter the HTTPS latest.json feed URL first, then click Save / Check online.',parent=self)
            return
        try:_validate_update_feed_url(url)
        except Exception as e:
            if manual: messagebox.showerror('Invalid update feed',str(e),parent=self)
            self.app_update_status.set(str(e)); return
        # Silent startup checks are limited to once every 12 hours.
        if not manual:
            stamp=str(self.config.get('last_update_check_utc','') or '')
            try:
                last=datetime.fromisoformat(stamp.replace('Z','+00:00'))
                if datetime.now(timezone.utc)-last<timedelta(hours=12): return
            except Exception: pass
        self.online_check_running=True
        if self.online_check_btn:self.online_check_btn.config(state='disabled')
        if self.online_download_btn:self.online_download_btn.config(state='disabled')
        self._set_online_progress('Checking for application updates…')
        def work():
            try:
                feed=fetch_update_feed(url)
                self.after(0,lambda f=feed:self._online_check_complete(f,manual))
            except Exception as e:
                self.after(0,lambda msg=str(e):self._online_check_failed(msg,manual))
        threading.Thread(target=work,daemon=True).start()

    def _online_check_complete(self,feed,manual):
        self.online_check_running=False; self.online_update_feed=feed
        self.config['last_update_check_utc']=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
        self.config['update_feed_url']=self.update_feed_url.get().strip(); save_config(self.config)
        if self.online_check_btn:self.online_check_btn.config(state='normal')
        ver=str(feed['version'])
        if version_tuple(ver)>version_tuple(VERSION):
            self.app_update_status.set(f'{APP_NAME} v{ver} is available. You are running v{VERSION}.')
            self.app_update_progress.set(0); self.app_update_percent.set('')
            if self.online_download_btn:self.online_download_btn.config(state='normal')
            try:self.tabs.select(self.updates_tab)
            except Exception:pass
        else:
            self.app_update_status.set(f'You are up to date. Latest release is v{ver}; running v{VERSION}.')
            self.app_update_progress.set(100); self.app_update_percent.set('100%')
            if self.online_download_btn:self.online_download_btn.config(state='disabled')
            if manual: messagebox.showinfo('No update needed',f'You are running the latest version (v{VERSION}).',parent=self)

    def _online_check_failed(self,message,manual):
        self.online_check_running=False
        if self.online_check_btn:self.online_check_btn.config(state='normal')
        if self.online_download_btn:self.online_download_btn.config(state='disabled')
        self.app_update_status.set(f'Online update check failed: {message}')
        self.app_update_progress.set(0); self.app_update_percent.set('')
        if manual: messagebox.showerror('Update check failed',message,parent=self)

    def download_online_update(self):
        if self.online_download_running:return
        feed=self.online_update_feed
        if not feed or version_tuple(feed.get('version','0'))<=version_tuple(VERSION):
            self.check_online_update(manual=True); return
        self.online_download_running=True
        if self.online_check_btn:self.online_check_btn.config(state='disabled')
        if self.online_download_btn:self.online_download_btn.config(state='disabled')
        self._set_online_progress(f'Downloading {APP_NAME} v{feed["version"]}…',0,int(feed.get('update_size') or 0))
        def report(message,done,total): self.after(0,lambda:self._set_online_progress(message,done,total))
        def work():
            try:
                path=download_feed_update(feed,report)
                self.after(0,lambda p=str(path):self._online_download_complete(p))
            except Exception as e:
                self.after(0,lambda msg=str(e):self._online_download_failed(msg))
        threading.Thread(target=work,daemon=True).start()

    def _online_download_complete(self,path):
        self.online_download_running=False
        if self.online_check_btn:self.online_check_btn.config(state='normal')
        self._set_online_progress('Download verified. Ready to install.',1,1)
        manifest=self.select_update_package(path)
        if manifest is None:return
        ver=str(manifest['version'])
        if messagebox.askyesno('Install downloaded update',f'{APP_NAME} v{ver} was downloaded and verified.\n\nInstall it now and restart?\n\nYour EVE data, routes, profiles, prices and settings will be preserved.',parent=self):
            self.install_selected_update(confirm=False)
        elif self.online_download_btn:
            self.online_download_btn.config(state='normal')

    def _online_download_failed(self,message):
        self.online_download_running=False
        if self.online_check_btn:self.online_check_btn.config(state='normal')
        if self.online_download_btn:self.online_download_btn.config(state='normal')
        self.app_update_status.set(f'Update download failed: {message}')
        self.app_update_progress.set(0); self.app_update_percent.set('')
        messagebox.showerror('Update download failed',message,parent=self)

    def command_line_update_path(self):
        """Return a .ejpupdate path passed by Windows file association, if any."""
        if len(sys.argv)<2:
            return None
        candidate=str(sys.argv[1]).strip().strip('"')
        if not candidate.lower().endswith(UPDATE_EXTENSION):
            return None
        path=Path(candidate).expanduser()
        return str(path.resolve()) if path.exists() else None

    def select_update_package(self,path):
        """Validate and select an update package in the Update Center."""
        path=str(path or '').strip()
        if not path:
            return None
        self.update_package_path.set(path)
        try:
            manifest=inspect_update_package(path)
            ver=str(manifest['version'])
            relation='newer' if version_tuple(ver)>version_tuple(VERSION) else 'not newer'
            self.app_update_status.set(f"Selected update: v{ver} • {manifest['mode']} • {relation} than v{VERSION}.")
            try:self.tabs.select(self.updates_tab)
            except Exception:pass
            return manifest
        except Exception as e:
            self.app_update_status.set(f'Invalid update package: {e}')
            return None

    def handle_command_line_update(self):
        path=self.pending_update_arg
        self.pending_update_arg=None
        if not path:
            return
        manifest=self.select_update_package(path)
        if manifest is None:
            messagebox.showerror('Invalid update package',self.app_update_status.get(),parent=self)
            return
        ver=str(manifest['version'])
        if version_tuple(ver)<=version_tuple(VERSION):
            messagebox.showinfo('Update file opened',f'This update contains {APP_NAME} v{ver}.\n\nYou are already running v{VERSION}, so no update is needed.',parent=self)
            return
        if messagebox.askyesno(f'{APP_NAME} update',f'Windows opened update v{ver}.\n\nInstall it over v{VERSION} now?\n\nYour EVE data, routes, profiles, market cache and settings will be preserved.',parent=self):
            self.install_selected_update(confirm=False)

    def choose_update_package(self):
        path=filedialog.askopenfilename(parent=self,title=f'Choose {APP_NAME} update file',filetypes=[(f'{APP_NAME} update','*.ejpupdate'),('All files','*.*')])
        if not path:return
        self.select_update_package(path)

    def install_selected_update(self,confirm=True):
        path=self.update_package_path.get().strip()
        if not path:
            self.choose_update_package(); path=self.update_package_path.get().strip()
            if not path:return
        try:
            manifest=inspect_update_package(path); ver=str(manifest['version'])
        except Exception as e:
            messagebox.showerror('Invalid update package',str(e),parent=self); return
        if confirm and not messagebox.askyesno('Install application update',f'Install {APP_NAME} v{ver} over v{VERSION}?\n\nYour EVE data, saved routes, profiles and settings will be preserved. A backup of the current app files will be created.',parent=self): return
        try:
            new_version,backup,helper=install_update_package(path)
        except Exception as e:
            messagebox.showerror('Update failed',str(e),parent=self); self.app_update_status.set(f'Update failed: {e}'); return
        self.app_update_status.set(f'Prepared v{new_version}. Backup: {backup}. Restarting…')
        save_config(self.config)
        messagebox.showinfo('Update ready',f'{APP_NAME} v{new_version} is verified and ready.\n\nThe app will now restart to finish the update.\n\nBackup: {backup}',parent=self)
        if helper is not None:
            try:
                subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except Exception as e:
                messagebox.showerror('Update helper failed',str(e),parent=self); return
            self.after(150,self._safe_destroy)
        else:
            self.restart_application()

    def restart_application(self):
        frozen=bool(getattr(sys,'frozen',False))
        if frozen:
            cmd=[str(Path(sys.executable).resolve())]
            cwd=str(Path(sys.executable).resolve().parent)
        else:
            target=APP_DIR/'app.py'
            exe=Path(sys.executable)
            if os.name=='nt':
                pythonw=exe.with_name('pythonw.exe')
                if pythonw.exists(): exe=pythonw
            cmd=[str(exe),str(target)]; cwd=str(APP_DIR)
        try:
            subprocess.Popen(cmd,cwd=cwd)
        except Exception as e:
            messagebox.showwarning('Restart needed',f'The update is installed, but automatic restart failed: {e}\n\nClose and reopen the app manually.',parent=self); return
        self.after(150,self._safe_destroy)

    def export_route_csv(self):
        if not self.last_route_export_rows:
            messagebox.showwarning('No route to export','Calculate a route first.',parent=self); return
        default='eve-jump-route.csv'
        start=self.route_from.get().strip().replace('/','-').replace('\\','-')
        dest=self.route_to.get().strip().replace('/','-').replace('\\','-')
        if start and dest: default=f'{start}-to-{dest}.csv'
        path=filedialog.asksaveasfilename(parent=self,title='Export route CSV',defaultextension='.csv',initialfile=default,filetypes=[('CSV files','*.csv'),('All files','*.*')])
        if not path:return
        with open(path,'w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f)
            w.writerow([APP_NAME,f'v{VERSION}'])
            w.writerow(['Route summary',self.last_route_summary])
            w.writerow([])
            w.writerow(['Leg','From','To','Region','Distance LY','Destination Security','NPC Stations','Cyno Type','Legality','Activity Score','Fuel Units','Fuel Cost ISK'])
            for row in self.last_route_export_rows:w.writerow(row)
        messagebox.showinfo('Route exported',f'Route saved to:\n{path}',parent=self)

    def copy_route_summary(self):
        if not self.last_route_export_rows:
            messagebox.showwarning('No route to copy','Calculate a route first.',parent=self); return
        lines=[self.last_route_summary,'']
        for leg,frm,to,region,dist,sec,stations,cyno,status,activity,fuel,cost in self.last_route_export_rows:
            lines.append(f'{leg}. {frm} → {to} | {dist} LY | {region} | sec {sec} | stations {stations} | {cyno} | {status} | activity {activity} | {fuel} fuel | {cost} ISK')
        text='\n'.join(lines)
        self.clipboard_clear(); self.clipboard_append(text); self.update_idletasks()
        self.route_summary.set(self.last_route_summary+' • copied to clipboard')

    def refresh_saved_lists(self):
        if hasattr(self,'profile_list'):
            self.profile_list.delete(0,'end')
            for name in sorted(self.config.get('profiles',{}),key=str.casefold): self.profile_list.insert('end',name)
        if hasattr(self,'saved_route_list'):
            self.saved_route_list.delete(0,'end')
            for name in sorted(self.config.get('routes',{}),key=str.casefold): self.saved_route_list.insert('end',name)

    def _selected_name(self,listbox,var):
        name=var.get().strip()
        if name: return name
        sel=listbox.curselection() if listbox else ()
        return listbox.get(sel[0]) if sel else ''

    def save_profile(self):
        name=self.profile_name.get().strip()
        if not name:
            messagebox.showwarning('Profile name','Enter a name for this profile.'); return
        self.config.setdefault('profiles',{})[name]={'ship':self.ship.get(),'jdc':self.jdc.get(),'jfc':self.jfc.get(),'jf':self.jf.get()}
        save_config(self.config); self.refresh_saved_lists(); self.saved_info.set(f'Saved profile “{name}”.')

    def load_profile(self):
        name=self._selected_name(self.profile_list,self.profile_name)
        p=self.config.get('profiles',{}).get(name)
        if not p:
            messagebox.showwarning('Profile not found','Select a saved profile or enter its exact name.'); return
        self.ship.set(normalize_ship_name(p.get('ship'), self.ship.get()))
        self.update_ship_controls()
        self.jdc.set(int(p.get('jdc',5))); self.jfc.set(int(p.get('jfc',5))); self.jf.set(int(p.get('jf',5)))
        self.profile_name.set(name); self.saved_info.set(f'Loaded profile “{name}”.')

    def delete_profile(self):
        name=self._selected_name(self.profile_list,self.profile_name)
        if not name or name not in self.config.get('profiles',{}): return
        if not messagebox.askyesno('Delete profile',f'Delete saved profile “{name}”?'): return
        del self.config['profiles'][name]; save_config(self.config); self.profile_name.set(''); self.refresh_saved_lists(); self.saved_info.set(f'Deleted profile “{name}”.')

    def _refresh_route_control_lists(self):
        self.waypoint_list.delete(0,'end')
        for name in self.waypoints:
            row=system(name); self.waypoint_list.insert('end',f'{name} — {row[7] if row else "Unknown region"}')
        self.avoid_list.delete(0,'end')
        for name in self.avoided_systems:
            row=system(name); self.avoid_list.insert('end',f'{name} — {row[7] if row else "Unknown region"}')

    def save_current_route(self):
        name=self.saved_route_name.get().strip()
        if not name:
            messagebox.showwarning('Route name','Enter a name for this route.'); return
        start=self.route_from.get().strip(); dest=self.route_to.get().strip()
        if not start or not dest:
            messagebox.showwarning('Route incomplete','Enter a start and destination before saving the route.'); return
        self.config.setdefault('routes',{})[name]={
            'start':start,'destination':dest,'waypoints':list(self.waypoints),'avoid_systems':list(self.avoided_systems),
            'avoid_regions':self.avoid_regions.get(),'security':self.route_sec.get(),'mode':self.route_mode.get(),
            'station_policy':self.route_station_policy.get(),
            'require_dest_station':bool(self.route_require_dest_station.get()),
            'enforce_legality':bool(self.enforce_legality.get()),'use_live_rules':bool(self.use_live_rules.get()),
            'ship':self.ship.get(),'jdc':self.jdc.get(),'jfc':self.jfc.get(),'jf':self.jf.get()
        }
        save_config(self.config); self.refresh_saved_lists(); self.saved_info.set(f'Saved route “{name}”.')

    def load_saved_route(self):
        name=self._selected_name(self.saved_route_list,self.saved_route_name)
        r=self.config.get('routes',{}).get(name)
        if not r:
            messagebox.showwarning('Route not found','Select a saved route or enter its exact name.'); return
        self.route_from.set(r.get('start','')); self.route_to.set(r.get('destination',''))
        self.waypoints=list(r.get('waypoints',[])); self.avoided_systems=list(r.get('avoid_systems',[])); self.avoid_regions.set(r.get('avoid_regions',''))
        if r.get('security') in ('All systems','Low + Null','Null only'): self.route_sec.set(r['security'])
        if r.get('mode') in ('Fewest Jumps','Shortest Distance'): self.route_mode.set(r['mode'])
        if r.get('station_policy') in ('Any systems','Prefer NPC stations','NPC stations only','Avoid NPC stations'): self.route_station_policy.set(r['station_policy'])
        self.route_require_dest_station.set(bool(r.get('require_dest_station',False)))
        self.enforce_legality.set(bool(r.get('enforce_legality',True))); self.use_live_rules.set(bool(r.get('use_live_rules',True)))
        self.ship.set(normalize_ship_name(r.get('ship'), self.ship.get()))
        self.update_ship_controls()
        self.jdc.set(int(r.get('jdc',self.jdc.get()))); self.jfc.set(int(r.get('jfc',self.jfc.get()))); self.jf.set(int(r.get('jf',self.jf.get())))
        self.saved_route_name.set(name); self._refresh_route_control_lists(); self.tabs.select(self.planner_tab)
        self.route_summary.set(f'Loaded saved route “{name}”. Click Find route to calculate it.')
        self.saved_info.set(f'Loaded route “{name}”.')

    def delete_saved_route(self):
        name=self._selected_name(self.saved_route_list,self.saved_route_name)
        if not name or name not in self.config.get('routes',{}): return
        if not messagebox.askyesno('Delete route',f'Delete saved route “{name}”?'): return
        del self.config['routes'][name]; save_config(self.config); self.saved_route_name.set(''); self.refresh_saved_lists(); self.saved_info.set(f'Deleted route “{name}”.')

    def find_range(self):
        sh=SHIPS[self.ship.get()]; maxr=sh['range']*(1+0.2*self.jdc.get())
        origin,rows=systems_in_range(self.range_origin.get(),maxr)
        if not origin: messagebox.showwarning('System not found','Enter an exact origin system name. Start typing and choose a system from the dropdown.'); return
        origin_ok,origin_reason=origin_legality(origin,sh)
        if self.range_legal_only.get() and not origin_ok:
            self.tree.delete(*self.tree.get_children())
            self.range_summary.set(f'Origin blocked for {self.ship.get()}: {origin_reason}.')
            return
        filt=self.sec_filter.get()
        def allowed_security(sec):
            if filt=='High-sec': return sec>=HIGHSEC_THRESHOLD
            if filt=='Low-sec': return 0.0<sec<HIGHSEC_THRESHOLD
            if filt=='Null-sec': return sec<=0.0
            return True
        self.tree.delete(*self.tree.get_children()); shown=0; legal_count=0; blocked_count=0; station_systems=0
        live=self.incursion_systems if self.use_live_rules.get() else set()
        station_filter=self.range_station_filter.get()
        for name,region,d,sec,station_count in rows:
            if not allowed_security(sec): continue
            if station_filter=='NPC station systems' and station_count<=0: continue
            if station_filter=='No NPC stations' and station_count>0: continue
            node=system(name)
            legal,cyno,reason=destination_legality(node,sh,live,self.use_live_rules.get())
            if legal: legal_count+=1
            else: blocked_count+=1
            if self.range_legal_only.get() and not legal: continue
            fuel=calc_fuel(d,sh,self.jfc.get(),self.ship_skill_level(sh))
            cost=self.fuel_cost(sh['isotope'],fuel)
            status='LEGAL ✓' if legal else 'BLOCKED — '+reason
            band=security_band(sec).replace('-sec','').lower()
            tags=(band,) if legal else (band,'blocked')
            station_text=str(station_count) if station_count else '—'
            if station_count: station_systems+=1
            self.tree.insert('', 'end', values=(name,region,f'{d:.3f}',f'{sec:.3f}',station_text,cyno,status,f'{fuel:,}',self.format_isk(cost)),tags=tags); shown+=1
        price=self.fuel_price(sh['isotope'])
        price_note=f' • {price:,.2f} ISK/unit' if price is not None else ' • price not set'
        legality_note=f' • {legal_count:,} legal / {blocked_count:,} blocked by jump rules' if not self.range_legal_only.get() else f' • {legal_count:,} legal destinations'
        station_note=f' • {station_systems:,} shown system(s) have NPC stations'
        self.range_summary.set(f'{shown:,} systems shown • {len(rows):,} geometrically within {maxr:.2f} LY of {origin[1]}{legality_note}{station_note} • {sh["isotope"]}{price_note}')
    def use_selected_origin(self):
        sel=self.tree.selection()
        if not sel: return
        name=self.tree.item(sel[0],'values')[0]; self.range_origin.set(name); self.find_range()
    def sort_tree(self,col):
        items=[(self.tree.set(i,col),i) for i in self.tree.get_children('')]
        numeric=col in ('distance','security','stations','fuel','cost')
        def key(x):
            if not numeric:return x[0].lower()
            try:return float(x[0].replace(',',''))
            except:return 0
        items.sort(key=key)
        for n,(_,i) in enumerate(items): self.tree.move(i,'',n)

    def add_waypoint(self):
        name=self.waypoint_input.get().strip()
        if not name: return
        row=system(name)
        if not row:
            messagebox.showwarning('System not found','Choose a valid waypoint system from the dropdown.'); return
        if row[1].casefold() not in {x.casefold() for x in self.waypoints}:
            self.waypoints.append(row[1]); self.waypoint_list.insert('end',f'{row[1]} — {row[7]}')
        self.waypoint_input.set('')

    def remove_waypoint(self):
        sel=self.waypoint_list.curselection()
        if not sel: return
        i=sel[0]; self.waypoint_list.delete(i); self.waypoints.pop(i)

    def add_avoid_system(self):
        name=self.avoid_input.get().strip()
        if not name: return
        row=system(name)
        if not row:
            messagebox.showwarning('System not found','Choose a valid system from the dropdown.'); return
        if row[1].casefold() not in {x.casefold() for x in self.avoided_systems}:
            self.avoided_systems.append(row[1]); self.avoid_list.insert('end',f'{row[1]} — {row[7]}')
        self.avoid_input.set('')

    def remove_avoid_system(self):
        sel=self.avoid_list.curselection()
        if not sel: return
        i=sel[0]; self.avoid_list.delete(i); self.avoided_systems.pop(i)

    def reverse_route(self):
        a,b=self.route_from.get(),self.route_to.get(); self.route_from.set(b); self.route_to.set(a)
        self.waypoints.reverse(); self.waypoint_list.delete(0,'end')
        for name in self.waypoints:
            row=system(name); self.waypoint_list.insert('end',f'{name} — {row[7] if row else "Unknown region"}')
        if self.route_from.get() and self.route_to.get(): self.find_route()

    def find_route(self):
        if not DB.exists(): messagebox.showwarning('EVE data missing','Update EVE data first.'); return
        sh=SHIPS[self.ship.get()]; maxr=sh['range']*(1+0.2*self.jdc.get())
        start_name=self.route_from.get().strip(); dest_name=self.route_to.get().strip()
        start_node=system(start_name); dest_node=system(dest_name)
        if not start_node or not dest_node:
            self.route_summary.set('System not found.'); messagebox.showwarning('System not found','Enter exact start and destination system names.'); return
        if self.route_require_dest_station.get() and (len(dest_node)<=8 or int(dest_node[8] or 0)<=0):
            self.route_summary.set(f'{dest_node[1]} has no NPC station. Disable the final-destination station requirement or choose another destination.')
            for v in (self.route_metric_jumps,self.route_metric_ly,self.route_metric_fuel,self.route_metric_cost,self.route_metric_stations): v.set('—')
            return
        if self.enforce_legality.get():
            ok,why=origin_legality(start_node,sh)
            if not ok:
                self.route_summary.set(f'Origin is not legal for {self.ship.get()}: {why}.'); return
            ok,cyno,why=destination_legality(dest_node,sh,self.incursion_systems,self.use_live_rules.get())
            if not ok:
                self.route_summary.set(f'Destination cannot be reached by jump drive: {why}.'); return
        avoid_regions=[x.strip() for x in self.avoid_regions.get().replace(';',',').split(',') if x.strip()]
        points=[start_name]+list(self.waypoints)+[dest_name]
        self.last_route_export_rows=[]; self.last_route_summary=''; self.last_route_nodes=[]; self.route_map_selected_index=None
        for v in (self.route_metric_jumps,self.route_metric_ly,self.route_metric_fuel,self.route_metric_cost,self.route_metric_stations): v.set('…')
        self.route_summary.set('Searching route…'); self.route_map_status.set('Searching route…'); self.update_idletasks(); self.route_tree.delete(*self.route_tree.get_children()); self.redraw_route_map()
        full_path=[]
        for seg in range(len(points)-1):
            self.route_summary.set(f'Searching segment {seg+1} of {len(points)-1}: {points[seg]} → {points[seg+1]}…'); self.update_idletasks()
            a,b,path=route_path(points[seg],points[seg+1],maxr,self.route_sec.get(),self.route_mode.get(),self.avoided_systems,avoid_regions,sh,self.enforce_legality.get(),self.incursion_systems,self.use_live_rules.get(),self.route_station_policy.get())
            if not a or not b:
                self.route_summary.set(f'System not found in segment {points[seg]} → {points[seg+1]}.'); return
            if not path:
                rules=' with jump legality enforced' if self.enforce_legality.get() else ''
                self.route_summary.set(f'No route found for {points[seg]} → {points[seg+1]} within {maxr:.2f} LY/jump using the current filters{rules}.'); return
            if full_path: full_path.extend(path[1:])
            else: full_path.extend(path)
        total_d=0.0; total_f=0; total_cost=0.0; has_price=self.fuel_price(sh['isotope']) is not None
        legal_legs=0; blocked_legs=0
        for i in range(len(full_path)-1):
            a,b=full_path[i],full_path[i+1]; d=distance_ly(a,b); fuel=calc_fuel(d,sh,self.jfc.get(),self.ship_skill_level(sh)); total_d+=d; total_f+=fuel
            cost=self.fuel_cost(sh['isotope'],fuel)
            if cost is not None: total_cost+=cost
            legal,cyno,reason=destination_legality(b,sh,self.incursion_systems,self.use_live_rules.get())
            if legal: legal_legs+=1
            else: blocked_legs+=1
            status='LEGAL ✓' if legal else 'BLOCKED — '+reason
            station_count=int(b[8] or 0) if len(b)>8 else 0
            act=activity_score(self._activity_record(b[0])) if hasattr(self,'activity_data') else 0
            row=(i+1,a[1],b[1],b[7],f'{d:.3f}',f'{b[5]:.3f}',(str(station_count) if station_count else '—'),cyno,status,str(act) if act else '—',f'{fuel:,}',self.format_isk(cost))
            band=security_band(b[5]).replace('-sec','').lower()
            tags=(band,) if legal else (band,'blocked')
            self.route_tree.insert('', 'end', values=row,tags=tags); self.last_route_export_rows.append(row)
        extras=[]
        if self.waypoints: extras.append(f'{len(self.waypoints)} waypoint(s)')
        if self.avoided_systems: extras.append(f'{len(self.avoided_systems)} avoided system(s)')
        if avoid_regions: extras.append(f'{len(avoid_regions)} avoided region(s)')
        if self.enforce_legality.get(): extras.append('jump legality enforced')
        if self.use_live_rules.get(): extras.append('live Incursion jams checked')
        if self.route_station_policy.get()!='Any systems': extras.append(self.route_station_policy.get())
        if self.route_require_dest_station.get(): extras.append('final NPC-station system required')
        if sh.get('class') in ('Supercarrier','Titan') and (self.route_station_policy.get()!='Any systems' or self.route_require_dest_station.get()):
            extras.append('station presence only — selected supercapital cannot dock in NPC stations')
        suffix=(' • '+', '.join(extras)) if extras else ''
        cost_note=f' • {self.format_isk(total_cost)} ISK fuel cost' if has_price else ' • fuel price not set'
        legality_note=f' • {legal_legs} legal leg(s)' if not blocked_legs else f' • WARNING: {blocked_legs} blocked leg(s)'
        station_stops=sum(1 for n in full_path[1:] if len(n)>8 and int(n[8] or 0)>0)
        self.last_route_summary=f'{len(full_path)-1} jumps • {total_d:.3f} LY total • {total_f:,} {sh["isotope"]}{cost_note}{legality_note} • {station_stops} station stop(s) • {self.route_mode.get()} • max {maxr:.2f} LY/jump{suffix}'
        self.route_metric_jumps.set(str(len(full_path)-1))
        self.route_metric_ly.set(f'{total_d:.2f} LY')
        self.route_metric_fuel.set(f'{total_f:,}')
        self.route_metric_cost.set((self.format_isk(total_cost)+' ISK') if has_price else '—')
        self.route_metric_stations.set(str(station_stops))
        self.last_route_nodes=list(full_path)
        self.route_map_zoom=1.0
        self.route_map_selected_index=0 if full_path else None
        self.route_summary.set(self.last_route_summary)
        self.record_recent_route(start_node[1],dest_node[1],len(full_path)-1,total_d,total_cost if has_price else None)
        self.redraw_route_map()
        self.refresh_dashboard()

    def route_map_fit(self):
        self.route_map_zoom=1.0
        self.redraw_route_map()

    def route_map_zoom_by(self,factor):
        try: factor=float(factor)
        except (TypeError,ValueError): return
        self.route_map_zoom=max(0.55,min(5.0,self.route_map_zoom*factor))
        self.redraw_route_map()

    def route_map_mousewheel(self,event):
        delta=getattr(event,'delta',0)
        if delta>0: self.route_map_zoom_by(1.15)
        elif delta<0: self.route_map_zoom_by(1/1.15)
        return 'break'

    def _schedule_route_map_redraw(self,event=None):
        if self.route_map_redraw_after:
            try: self.after_cancel(self.route_map_redraw_after)
            except Exception: pass
        self.route_map_redraw_after=self.after(80,self.redraw_route_map)

    def _route_map_axes(self,nodes):
        # Pick the two SDE coordinate axes with the largest route spans. This preserves
        # a useful spatial view without pretending that the 2D projection is a stargate map.
        coords=[[float(n[2]),float(n[3]),float(n[4])] for n in nodes]
        spans=[]
        for axis in range(3):
            vals=[c[axis] for c in coords]
            spans.append((max(vals)-min(vals) if vals else 0.0,axis))
        spans.sort(reverse=True)
        a=spans[0][1] if spans else 0
        b=spans[1][1] if len(spans)>1 else (1 if a!=1 else 2)
        return a,b,('X','Y','Z')[a],('X','Y','Z')[b]

    def _route_map_positions(self,width,height):
        nodes=self.last_route_nodes
        if not nodes: return [],('X','Y')
        ax,ay,ax_name,ay_name=self._route_map_axes(nodes)
        raw=[(float(n[2]),float(n[3]),float(n[4])) for n in nodes]
        xs=[c[ax] for c in raw]; ys=[c[ay] for c in raw]
        xmin,xmax=min(xs),max(xs); ymin,ymax=min(ys),max(ys)
        dx=max(xmax-xmin,LY_METERS*0.25); dy=max(ymax-ymin,LY_METERS*0.25)
        pad=46.0
        usable_w=max(20.0,width-2*pad); usable_h=max(20.0,height-2*pad)
        base=min(usable_w/dx,usable_h/dy)*self.route_map_zoom
        cx=(xmin+xmax)/2.0; cy=(ymin+ymax)/2.0
        screen=[]
        for c in raw:
            x=width/2.0+(c[ax]-cx)*base
            y=height/2.0-(c[ay]-cy)*base
            screen.append((x,y))
        return screen,(ax_name,ay_name)

    def redraw_route_map(self):
        if not hasattr(self,'route_map_canvas'): return
        self.route_map_redraw_after=None
        c=self.route_map_canvas; c.delete('all'); self.route_map_hitboxes=[]
        w=max(c.winfo_width(),480); h=max(c.winfo_height(),260)
        # Tactical HUD background: quiet grid + deterministic star specks.
        for gx in range(0,int(w)+1,64): c.create_line(gx,0,gx,h,fill='#101b25')
        for gy in range(0,int(h)+1,64): c.create_line(0,gy,w,gy,fill='#101b25')
        c.create_line(w/2,0,w/2,h,fill='#152735'); c.create_line(0,h/2,w,h/2,fill='#152735')
        for i in range(42):
            sx=(i*97+31)%max(1,int(w)); sy=(i*53+19)%max(1,int(h)); rr=1 if i%5 else 1.5
            c.create_oval(sx-rr,sy-rr,sx+rr,sy+rr,fill='#203646',outline='')
        nodes=self.last_route_nodes
        if not nodes:
            c.create_text(w/2,h/2-8,text='NO ROUTE TELEMETRY',fill='#7d93a4',font=('Segoe UI Semibold',13))
            c.create_text(w/2,h/2+16,text='Calculate a route to initialise the tactical projection',fill='#526879',font=('Segoe UI',9))
            self.route_map_status.set('Calculate a route to display its SDE-coordinate map.')
            return
        pos,axes=self._route_map_positions(w,h)
        c.create_text(10,10,anchor='nw',text=f'Projection: {axes[0]} / {axes[1]}   •   Zoom {self.route_map_zoom:.2f}×',fill='#8090a0',font=('Segoe UI',9))

        # Project the selected hull's true LY sphere as a tactical 2D radius ring.
        if self.route_map_show_radius.get() and nodes:
            sel=self.route_map_selected_index if self.route_map_selected_index is not None and self.route_map_selected_index<len(nodes) else 0
            ax,ay,_,_=self._route_map_axes(nodes); raw=[(float(n[2]),float(n[3]),float(n[4])) for n in nodes]; xs=[q[ax] for q in raw]; ys=[q[ay] for q in raw]
            dx=max(max(xs)-min(xs),LY_METERS*0.25); dy=max(max(ys)-min(ys),LY_METERS*0.25); pad=46.0; base=min(max(20.0,w-2*pad)/dx,max(20.0,h-2*pad)/dy)*self.route_map_zoom
            maxr=SHIPS[self.ship.get()]['range']*(1+0.2*self.jdc.get()); rp=maxr*LY_METERS*base; sx,sy=pos[sel]
            c.create_oval(sx-rp,sy-rp,sx+rp,sy+rp,outline='#245a70',width=1,dash=(5,4))
            c.create_text(sx+min(rp,120),sy-rp if rp<140 else max(18,sy-125),text=f'{maxr:.1f} LY envelope',fill='#4d91ad',font=('Segoe UI',8))

        # Legs first so nodes sit above the connectors.
        for i in range(len(nodes)-1):
            x1,y1=pos[i]; x2,y2=pos[i+1]
            d=distance_ly(nodes[i],nodes[i+1])
            c.create_line(x1,y1,x2,y2,fill='#0a3548',width=7)
            c.create_line(x1,y1,x2,y2,fill='#60c9ec',width=2,arrow='last',arrowshape=(8,10,4))
            mx,my=(x1+x2)/2.0,(y1+y2)/2.0
            c.create_rectangle(mx-27,my-10,mx+27,my+10,fill='#0b1118',outline='')
            c.create_text(mx,my,text=f'{d:.2f} LY',fill='#b8c5d1',font=('Segoe UI',8))

        waypoint_names={x.casefold() for x in self.waypoints}
        for i,(node,(x,y)) in enumerate(zip(nodes,pos)):
            sec=float(node[5]); band=security_band(sec)
            fill='#5ebd77' if band=='High-sec' else ('#d9a441' if band=='Low-sec' else '#d86161')
            selected=(i==self.route_map_selected_index)
            r=7 if i in (0,len(nodes)-1) else 6
            if i==0:
                c.create_rectangle(x-r,y-r,x+r,y+r,fill=fill,outline='#ffffff' if selected else '#dfe8f0',width=2 if selected else 1)
            elif i==len(nodes)-1:
                c.create_polygon(x,y-r-2,x+r+2,y,x,y+r+2,x-r-2,y,fill=fill,outline='#ffffff' if selected else '#dfe8f0',width=2 if selected else 1)
            else:
                c.create_oval(x-r,y-r,x+r,y+r,fill=fill,outline='#ffffff' if selected else '#dfe8f0',width=2 if selected else 1)
            if node[1].casefold() in waypoint_names:
                c.create_oval(x-r-4,y-r-4,x+r+4,y+r+4,outline='#65c7d0',width=2)
            station_count=int(node[8] or 0) if len(node)>8 else 0
            if self.route_map_show_stations.get() and station_count>0:
                c.create_rectangle(x-r-6,y-r-6,x+r+6,y+r+6,outline='#9be7ff',width=1,dash=(3,2))
                c.create_text(x+r+9,y-r-8,text='▣',anchor='sw',fill='#9be7ff',font=('Segoe UI',8,'bold'))
            self.route_map_hitboxes.append((x,y,16,i))
            show_label=self.route_map_show_labels.get() and (len(nodes)<=24 or i in (0,len(nodes)-1) or node[1].casefold() in waypoint_names or selected)
            if show_label:
                label=node[1]
                if self.route_map_show_regions.get(): label+=f' — {node[7]}'
                if self.route_map_show_stations.get() and len(node)>8 and int(node[8] or 0)>0: label+=f'  ▣{int(node[8])}'
                anchor='sw' if y>30 else 'nw'
                offy=-9 if anchor=='sw' else 9
                c.create_text(x+9,y+offy,text=label,anchor=anchor,fill='#e6edf3',font=('Segoe UI',9,'bold' if i in (0,len(nodes)-1) else 'normal'))

        if self.route_map_selected_index is None or self.route_map_selected_index>=len(nodes):
            self.route_map_selected_index=0
        self._route_map_update_status()

    def _route_map_update_status(self):
        if not self.last_route_nodes or self.route_map_selected_index is None:
            self.route_map_status.set('Click for details • right-click for EVE destination/waypoint actions • double-click for Systems in Range.')
            return
        i=max(0,min(self.route_map_selected_index,len(self.last_route_nodes)-1)); n=self.last_route_nodes[i]
        station_count=int(n[8] or 0) if len(n)>8 else 0
        parts=[f'{n[1]} — {n[7]}',f'sec {float(n[5]):.3f} ({security_band(n[5])})',f'NPC stations {station_count}',f'node {i+1}/{len(self.last_route_nodes)}']
        if i>0: parts.append(f'incoming {distance_ly(self.last_route_nodes[i-1],n):.3f} LY')
        if i<len(self.last_route_nodes)-1: parts.append(f'outgoing {distance_ly(n,self.last_route_nodes[i+1]):.3f} LY')
        self.route_map_status.set(' • '.join(parts))

    def route_map_click(self,event):
        if not self.route_map_hitboxes: return
        best=None
        for x,y,r,i in self.route_map_hitboxes:
            d=(event.x-x)**2+(event.y-y)**2
            if d<=r*r and (best is None or d<best[0]): best=(d,i)
        if best is None: return
        self.route_map_selected_index=best[1]
        if self.route_map_selected_index>0:
            children=self.route_tree.get_children()
            idx=self.route_map_selected_index-1
            if idx<len(children):
                self.route_tree.selection_set(children[idx]); self.route_tree.focus(children[idx]); self.route_tree.see(children[idx])
        else:
            self.route_tree.selection_remove(self.route_tree.selection())
        self.redraw_route_map()

    def route_map_use_selected_origin(self):
        if not self.last_route_nodes or self.route_map_selected_index is None:
            messagebox.showinfo('Route map','Select a system on the route map first.'); return
        n=self.last_route_nodes[self.route_map_selected_index]
        self.range_origin.set(n[1])
        self.tabs.select(self.range_tab)
        self.find_range()

    def calculate(self):
        a=system(self.frm.get()); b=system(self.to.get())
        if not a or not b: messagebox.showwarning('System not found','Enter exact system names. Start typing and choose a system from the dropdown.'); return
        sh=SHIPS[self.ship.get()]; d=distance_ly(a,b); maxr=sh['range']*(1+0.2*self.jdc.get()); fuel=calc_fuel(d,sh,self.jfc.get(),self.ship_skill_level(sh)); in_range=d<=maxr+1e-9
        origin_ok,origin_reason=origin_legality(a,sh)
        legal,cyno,legal_reason=destination_legality(b,sh,self.incursion_systems,self.use_live_rules.get())
        fully_ok=in_range and origin_ok and legal
        jf_line=(f"Jump Freighters:   {self.jf.get()}\n" if sh.get('jf_bonus') else '')
        bay=sh.get('fuel_bay_m3'); bay_line=(f"Fuel bay:          {bay:,} m³\n" if bay else '')
        price=self.fuel_price(sh['isotope']); cost=self.fuel_cost(sh['isotope'],fuel)
        price_line=(f"Isotope price:     {price:,.2f} ISK/unit\nFuel cost:         {self.format_isk(cost)} ISK\n" if price is not None else "Isotope price:     Not set (Fuel Prices tab)\nFuel cost:         —\n")
        cynos=', '.join(ship_cyno_types(sh))
        jump_status='JUMP LEGAL ✓' if fully_ok else 'JUMP NOT LEGAL ✗'
        range_status='IN RANGE ✓' if in_range else 'OUT OF RANGE ✗'
        legality_status=('LEGAL ✓ — '+legal_reason) if legal else ('BLOCKED ✗ — '+legal_reason)
        origin_status=('OK ✓ — '+origin_reason) if origin_ok else ('BLOCKED ✗ — '+origin_reason)
        live_note='Enabled (current Incursion systems from CCP ESI)' if self.use_live_rules.get() else 'Disabled (static rules only)'
        from_stations=int(a[8] or 0) if len(a)>8 else 0
        to_stations=int(b[8] or 0) if len(b)>8 else 0
        self.write(f"{a[1]}  →  {b[1]}\n\nShip:              {self.ship.get()}\nClass:             {sh.get('class','Unknown')}\nDistance:          {d:.3f} LY\nMaximum range:     {maxr:.2f} LY (JDC {self.jdc.get()})\nRange:             {range_status}\nOverall status:    {jump_status}\n\nOrigin legality:   {origin_status}\nDestination:       {legality_status}\nPreferred cyno:    {cyno if legal else '—'}\nSupported cynos:   {cynos}\nLive rules:        {live_note}\n\nFuel type:         {sh['isotope']}\nBase fuel / LY:    {sh['fuel']:,} units\nJFC:               {self.jfc.get()}\n{jf_line}{bay_line}Fuel required:     {fuel:,} units\n{price_line}\nFrom security:     {a[5]:.3f} ({security_band(a[5])})\nTo security:       {b[5]:.3f} ({security_band(b[5])})\nFrom region:       {a[7]}\nTo region:         {b[7]}\nFrom NPC stations: {from_stations}\nTo NPC stations:   {to_stations}\n\nStation data is NPC-station presence from CCP SDE. Supercarriers/titans cannot dock in NPC stations, and player-owned Upwell structures are not globally discoverable through public ESI.\n\nNote: active sovereignty cyno jammers and grid-local inhibitors are not reliably available from public ESI; verify those in the EVE client before committing a jump.\n")

if __name__=='__main__':
    # Build/runtime smoke-test mode: reaching this point proves that the frozen
    # executable successfully loaded its bundled Python runtime and imports.
    if '--build-smoke-test' in sys.argv:
        raise SystemExit(0)
    App().mainloop()
