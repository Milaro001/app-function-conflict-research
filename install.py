#!/usr/bin/env python3
"""Install App research V1.1 and its pinned PPT Skills into the selected Agent."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

HOSTS={'agents':'.agents','codex':'.codex','claude':'.claude','cursor':'.cursor','gemini':'.gemini',
       'workbuddy':'.workbuddy','workbuddy-intl':'.workbuddy-ai','codebuddy':'.codebuddy'}


def main():
    root=Path(__file__).resolve().parent
    source=root/'skills/contradiction-review-v1'
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--agent',choices=HOSTS,default='agents')
    p.add_argument('--project',type=Path)
    p.add_argument('--destination',type=Path,help='Exact main Skill folder')
    p.add_argument('--workspace',type=Path)
    p.add_argument('--python',type=Path)
    p.add_argument('--browser',type=Path)
    p.add_argument('--mirror',choices=['default','china'],default='default')
    p.add_argument('--full',action='store_true')
    p.add_argument('--install-node',action='store_true')
    p.add_argument('--no-setup',action='store_true')
    p.add_argument('--no-delivery-skills',action='store_true')
    p.add_argument('--no-presentation-setup',action='store_true')
    p.add_argument('--replace',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    base=a.project.expanduser().resolve() if a.project else Path.home()
    target=a.destination.expanduser().resolve() if a.destination else base/HOSTS[a.agent]/'skills/contradiction-review-v1'
    if not (source/'SKILL.md').is_file():p.error('Keep install.py beside skills/contradiction-review-v1')
    if source.resolve()==target or source.resolve() in target.parents:p.error('Install outside the delivery source')
    if a.dry_run:
        print(json.dumps({'dry_run':True,'destination':str(target),'dependency_parent':str(target.parent),
                          'setup':not a.no_setup,'delivery_skills':not a.no_delivery_skills},ensure_ascii=False,indent=2));return 0
    backup=None
    if target.exists():
        if not a.replace:p.error('Destination exists; --replace keeps a backup before updating')
        backup=target.with_name(target.name+'.backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        target.rename(backup)
    try:
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(source,target,ignore=shutil.ignore_patterns('.venv','.setup','__pycache__','*.pyc','.env'))
        if backup and (backup/'runtime.json').is_file():
            shutil.copy2(backup/'runtime.json',target/'runtime.json')
    except Exception:
        if target.exists():shutil.rmtree(target)
        if backup:backup.rename(target)
        raise
    result={'installed':str(target),'backup':str(backup) if backup else None,'login_performed':False}
    if not a.no_delivery_skills:
        cmd=[sys.executable,str(target/'scripts/bootstrap_delivery_skills.py'),'--install','--mirror',a.mirror]
        bundle=root/'bundled-skills'
        if bundle.is_dir():cmd+=['--bundle',str(bundle)]
        result['delivery_skill_install_exit']=subprocess.call(cmd)
    if not a.no_setup:
        cmd=[sys.executable,str(target/'scripts/setup.py'),'--mirror',a.mirror]
        for flag,value in [('--workspace',a.workspace),('--python',a.python),('--browser',a.browser)]:
            if value:cmd+=[flag,str(value.expanduser())]
        if a.full:cmd+=['--full']
        if a.install_node:cmd+=['--install-node']
        result['collection_setup_exit']=subprocess.call(cmd)
        cfg=json.loads((target/'runtime.json').read_text(encoding='utf-8'))
        python=Path(cfg['python'])
        if not python.is_absolute():python=target/python
        if not a.no_delivery_skills and not a.no_presentation_setup and python.is_file() and result['collection_setup_exit'] in (0,2):
            result['presentation_setup_exit']=subprocess.call([str(python),str(target/'scripts/bootstrap_delivery_skills.py'),'--install-runtime','--mirror',a.mirror])
    result['meaning']='Skill files installed; inspect setup reports for actual runtime capabilities. No login or collection was performed.'
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if any(v not in (0,None) for k,v in result.items() if k.endswith('_exit')) else 0


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(errors='backslashreplace')
    raise SystemExit(main())
