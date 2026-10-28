#!/usr/bin/env python3
"""Inspect or install pinned presentation Skills. No accounts or collection are used."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

SKILL = Path(__file__).resolve().parents[1]


def dependencies():
    return json.loads((SKILL/'references/delivery-dependencies.json').read_text(encoding='utf-8'))['presentation_skills']


def acquire(item, target, bundle=None):
    source = Path(bundle)/item['name'] if bundle else None
    if source and (source/'SKILL.md').is_file():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns('.venv', '.git', '__pycache__', '*.pyc', '.env'))
        return 'bundled'
    repo, commit, subpath = item['repository'], item['commit'], item['path']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid pinned source identity')
    url = 'https://codeload.github.com/{}/zip/{}'.format(repo, commit)
    req = urllib.request.Request(url, headers={'User-Agent':'App-Research-Skill-Installer/1.0'})
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read(100*1024*1024+1)
    if len(raw)>100*1024*1024:
        raise ValueError('Source archive exceeds installer limit')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive, tempfile.TemporaryDirectory() as temp:
        names=archive.namelist()
        prefix=names[0].split('/')[0]+'/'
        selected=prefix+(subpath.rstrip('/')+'/' if subpath else '')
        files=[info for info in archive.infolist() if info.filename.startswith(selected) and not info.is_dir()]
        if sum(info.file_size for info in files)>200*1024*1024:
            raise ValueError('Unpacked source exceeds installer limit')
        stage=Path(temp)/'skill';stage.mkdir()
        for info in files:
            rel=PurePosixPath(info.filename[len(selected):])
            if rel.is_absolute() or '..' in rel.parts or ((info.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('Unsafe source archive member')
            file=stage/Path(*rel.parts);file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(archive.read(info))
        if not (stage/'SKILL.md').is_file():
            raise ValueError('Pinned Skill entry missing')
        license_name=item.get('license_path')
        if license_name and not (stage/'LICENSE').exists():
            (stage/'LICENSE').write_bytes(archive.read(prefix+license_name))
        shutil.copytree(stage,target)
    return 'pinned-official-source'


def runtime_check():
    modules={'pptx':'python-pptx','xlsxwriter':'XlsxWriter','PIL':'Pillow','yaml':'PyYAML','flask':'Flask',
             'pathops':'skia-pathops','uharfbuzz':'uharfbuzz','fontTools':'fonttools','requests':'requests'}
    return {package:importlib.util.find_spec(module) is not None for module,package in modules.items()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination',type=Path,default=SKILL.parent)
    p.add_argument('--bundle',type=Path)
    p.add_argument('--install',action='store_true')
    p.add_argument('--check',action='store_true',help='Inspect without installing')
    p.add_argument('--install-runtime',action='store_true')
    p.add_argument('--mirror',choices=['default','china'],default='default')
    a=p.parse_args();target=a.destination.expanduser().resolve();rows=[]
    for item in dependencies():
        folder=target/item['name']
        result={'name':item['name'],'path':str(folder),'present':(folder/'SKILL.md').is_file()}
        if a.install and not result['present']:
            try:
                folder.parent.mkdir(parents=True,exist_ok=True)
                result['installed_from']=acquire(item,folder,a.bundle)
                result['present']=True
            except Exception as exc:
                result['error']=str(exc)
                if folder.exists():shutil.rmtree(folder)
        rows.append(result)
    if a.install_runtime:
        cmd=[sys.executable,'-m','pip','install','--disable-pip-version-check','-r',str(SKILL/'requirements-presentations.txt')]
        if a.mirror=='china':cmd+=['--index-url','https://pypi.tuna.tsinghua.edu.cn/simple']
        code=subprocess.call(cmd)
    else:code=0
    check=runtime_check()
    result={'skills':rows,'runtime_packages':check,'runtime_ready':all(check.values()),
            'skills_present':all(r['present'] for r in rows),'runtime_install_exit':code,
            'external_word_excel_plugins_bundled':False,'login_performed':False}
    if a.install or a.install_runtime:
        (SKILL/'.setup').mkdir(exist_ok=True)
        (SKILL/'.setup/delivery-tools.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    ok=result['skills_present'] and code==0
    if a.check or a.install_runtime:ok=ok and result['runtime_ready']
    return 0 if ok else 2


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(errors='backslashreplace')
    raise SystemExit(main())
