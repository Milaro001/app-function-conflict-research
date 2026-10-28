#!/usr/bin/env python3
"""Configure an extracted/installed self-contained skill; never logs in or collects."""
import argparse,json,os,shutil,sys
from pathlib import Path

def detect_browser():
    candidates=[Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')]
    for name in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
        if os.environ.get(name):
            folder=Path(os.environ[name]);candidates.extend([folder/'Microsoft/Edge/Application/msedge.exe',folder/'Google/Chrome/Application/chrome.exe'])
    for name in ('microsoft-edge','microsoft-edge-stable','google-chrome','chromium','chromium-browser'):
        found=shutil.which(name)
        if found:candidates.append(Path(found))
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:candidates.append(Path(runtime.chromium.executable_path))
    except ImportError:pass
    return next((p.absolute() for p in candidates if p.is_file()),None)

def main():
    if sys.version_info<(3,11):raise SystemExit('Python 3.11+ is required; 3.12 is recommended.')
    skill=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,default=Path.cwd());p.add_argument('--python',type=Path,default=Path(sys.executable));p.add_argument('--browser',type=Path);p.add_argument('--mediacrawler',type=Path,default=skill/'vendor/MediaCrawler');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    workspace=a.workspace.expanduser().resolve();python=a.python.expanduser().absolute();vendor=a.mediacrawler.expanduser().resolve()
    if not python.is_file():p.error('--python executable does not exist')
    if not (vendor/'LICENSE').is_file():p.error('Bundled MediaCrawler is missing; use the complete delivery or provide --mediacrawler')
    browser=a.browser.expanduser().absolute() if a.browser else detect_browser()
    if a.browser and not browser.is_file():p.error('--browser executable does not exist')
    cfg=json.loads((skill/'runtime.json').read_text(encoding='utf-8'))
    cfg.update(workspace=str(workspace),python=str(python),mediacrawler=str(vendor),runtime=str(workspace/'.app-conflict-runtime'),output=str(workspace/'output/app-conflict-research'),browser_executable=str(browser or workspace/'.setup/browser-not-selected'),cached_sources={})
    if not a.dry_run:
        target=skill/'runtime.json';temp=target.with_suffix('.json.tmp');temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(target)
    print(json.dumps({'configured':not a.dry_run,'browser_found':bool(browser),'configuration':cfg},ensure_ascii=False,indent=2))
if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
