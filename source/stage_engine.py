"""Collect a relocatable GStreamer subset and its PE import closure."""
from pathlib import Path
import shutil
import json
import pefile
import argparse

ROOT = Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser()
parser.add_argument('--prefix',type=Path,default=ROOT/'work/toolchain/msys64/ucrt64')
parser.add_argument('--receiver',type=Path,default=ROOT/'work/engine-build/uxplay.exe')
parser.add_argument('--destination',type=Path,default=ROOT/'outputs/AirFrame/engine')
options=parser.parse_args()
PREFIX = options.prefix
DEST = options.destination
DEST.mkdir(parents=True,exist_ok=True)
PLUGINS = DEST/'plugins'; PLUGINS.mkdir(exist_ok=True)
plugins = ['coreelements','app','playback','typefindfunctions','videoparsersbad',
           'libav','autodetect','wasapi','audioparsers','audioconvert','audioresample',
           'd3d11','videoconvertscale','jpeg','volume','videotestsrc','audiotestsrc',
           'directsound','isomp4','matroska','id3demux','rawparse','level']
queue = []
def put(src,dest):
    shutil.copy2(src,dest); queue.append(Path(dest))

put(options.receiver,DEST/'uxplay.exe')
for name in plugins:
    file = PREFIX/'lib/gstreamer-1.0'/f'libgst{name}.dll'
    if file.exists(): put(file,PLUGINS/file.name)
    else: print('Unavailable plugin:',name)
for name in ['gst-inspect-1.0.exe','gst-launch-1.0.exe']:
    put(PREFIX/'bin'/name,DEST/name)
scanner = PREFIX/'libexec/gstreamer-1.0/gst-plugin-scanner.exe'
put(scanner,DEST/scanner.name)
available = {p.name.lower():p for p in (PREFIX/'bin').glob('*.dll')}
copied = set(); system = set()
while queue:
    path = queue.pop()
    with pefile.PE(str(path),fast_load=True) as pe:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
        entries = list(getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]))+list(getattr(pe,'DIRECTORY_ENTRY_DELAY_IMPORT',[]))
        for entry in entries:
            name = entry.dll.decode().lower()
            if name in available and name not in copied:
                copied.add(name); put(available[name],DEST/available[name].name)
            elif name not in available:
                system.add(name)
manifest = {'prefix':'MSYS2 UCRT64','plugins':plugins,'runtime_dlls':sorted(copied),'system_imports':sorted(system)}
(DEST/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2))
print(f'Staged {len(copied)} DLLs, {len(plugins)} requested plugins')
print(f'Size: {sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())/1024**2:.1f} MiB')
