"""Opt-in bounded acquisition of two reviewed licensed test sources; never runs on requests."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

SOURCES = {
    'labrador.jpg': dict(url='https://upload.wikimedia.org/wikipedia/commons/6/60/YellowLabradorLooking.jpg',
        page='https://commons.wikimedia.org/wiki/File:YellowLabradorLooking.jpg',bytes=140606,sha1='cc9eceb545a53e93e5e028d6f2fa4988f754890d',
        revision='2009-11-30T21:15:37Z',license='CC-BY-SA-3.0',license_url='https://creativecommons.org/licenses/by-sa/3.0/',
        attribution='Photograph: Elf (October 2004, Turlock, California); color revision: Carla Nunziata. CC BY-SA 3.0. Original Wikimedia file, not the owner-removed retouched variant.'),
    'jijiga.ogv': dict(url='https://upload.wikimedia.org/wikipedia/commons/7/74/Jijiga.ogv',
        page='https://commons.wikimedia.org/wiki/File:Jijiga.ogv',bytes=18214298,sha1='93544a2bafcc212927c7d6c3e4789853c07ecea4',
        revision='2011-04-08T06:25:23Z',license='CC0-1.0',license_url='https://creativecommons.org/publicdomain/zero/1.0/',
        attribution='Brian Dell, own traffic footage at Jijiga, Ethiopia, 5 January 2011; CC0 1.0. No camera identity or activity allegation inferred.')}


def acquire(root,approved_bytes):
    if not sum(s['bytes'] for s in SOURCES.values()) <= approved_bytes <= 20_000_000:
        raise ValueError('Explicit reviewed source-download budget required, maximum 20 MB')
    folder=Path(root)/'visual-test-media'
    folder.mkdir(parents=True,exist_ok=True)
    receipt={}
    transferred=0
    for name,info in SOURCES.items():
        target=folder/name
        if not target.exists():
            temporary=target.with_suffix('.part')
            received=0
            with urlopen(Request(info['url'],headers={'User-Agent':'AcademicEvidenceSystem/0.5 (local academic verification)'}),timeout=90) as response, temporary.open('wb') as output:
                while block:=response.read(1024*1024):
                    received+=len(block)
                    transferred+=len(block)
                    if received>info['bytes'] or transferred>approved_bytes:
                        raise ValueError('Source download budget exceeded')
                    output.write(block)
            if received!=info['bytes'] or hashlib.sha1(temporary.read_bytes()).hexdigest()!=info['sha1']:
                raise ValueError('Source does not match the reviewed publisher version')
            temporary.replace(target)
        content=target.read_bytes()
        if len(content)!=info['bytes'] or hashlib.sha1(content).hexdigest()!=info['sha1']:
            raise ValueError('Existing reviewed source failed integrity verification; do not overwrite')
        receipt[name]={**info,'sha256':hashlib.sha256(content).hexdigest()}
    derivative=folder/'jijiga-960.mp4'
    manifest=folder/'provenance.json'
    if derivative.exists():
        prior=json.loads(manifest.read_text())
        if hashlib.sha256(derivative.read_bytes()).hexdigest()!=prior['jijiga-960.mp4']['sha256']:
            raise ValueError('Existing MP4 derivative failed integrity check')
        receipt['jijiga-960.mp4']=prior['jijiga-960.mp4']
    else:
        command=['ffmpeg','-v','error','-nostdin','-threads','2','-protocol_whitelist','file','-i',str(folder/'jijiga.ogv'),
            '-map','0:v:0','-an','-vf','scale=960:-2','-c:v','libx264','-threads','2','-preset','veryfast','-crf','23','-movflags','+faststart',str(derivative)]
        subprocess.run(command,capture_output=True,check=True,timeout=120)
        receipt['jijiga-960.mp4']=dict(source='jijiga.ogv',license='CC0-1.0',sha256=hashlib.sha256(derivative.read_bytes()).hexdigest(),
            bytes=derivative.stat().st_size,transformation='Full real source footage, scaled to 960 pixels wide, H.264 CRF 23, audio omitted; no synthetic frames or claims of camera-original MP4.',command=command[1:])
    manifest.write_text(json.dumps(receipt,indent=2))
    return dict(transferred_bytes=transferred,sources={name:{'bytes':value['bytes'],'sha256':value['sha256'],'license':value['license']} for name,value in receipt.items()})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--approved-bytes',type=int,required=True)
    args=parser.parse_args()
    print(json.dumps(acquire(args.root,args.approved_bytes),indent=2))
