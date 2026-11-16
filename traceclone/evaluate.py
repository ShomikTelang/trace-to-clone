"""Independent behavioral smoke tests for a running clone.

Goal predicates use privileged state access; the browser agent is never given
this verifier token. API smoke and GUI smoke are separate reports.
"""
import json
import os
from pathlib import Path
from urllib import error, request


def http(base_url, path, method='GET', body=None, verifier_key=None):
    headers={}
    if body is not None:headers['Content-Type']='application/json'
    if verifier_key:headers['X-Verifier-Key']=verifier_key
    req=request.Request(base_url.rstrip('/')+path,
                        data=json.dumps(body).encode() if body is not None else None,
                        headers=headers,method=method)
    try:
        with request.urlopen(req,timeout=10) as response:
            return json.loads(response.read())
    except error.HTTPError as e:
        raise RuntimeError(f'{method} {path}: HTTP {e.code} {e.read().decode()[:400]}') from e


def run_api_smoke(url, key='local-dev-verifier'):
    checks=[]
    def record(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    try:
        spec=http(url,'/api/spec')
        record('spec exposes at least two columns',len(spec['columns'])>=2)
        http(url,'/internal/reset','POST',verifier_key=key)
        initial=http(url,'/api/tasks')
        record('reset returns exact seed count',len(initial)==3 if spec.get('app_id')=='kanboard_mvp' else True)
        target_col=spec['columns'][1]['id']
        title='TC smoke: test task'
        task=http(url,'/api/tasks','POST',{'title':title,'priority':spec['default_priority']})
        record('creation persisted',any(t['id']==task['id'] for t in http(url,'/api/tasks')))
        task=http(url,f'/api/tasks/{task["id"]}','PATCH',{'column':target_col,'tags':['research','smoke']})
        record('move and tags stored',task['column']==target_col and 'smoke' in task['tags'])
        task=http(url,f'/api/tasks/{task["id"]}/close','POST')
        record('closed task hidden from default listing',not any(t['id']==task['id'] for t in http(url,'/api/tasks')))
        record('closed task persisted',any(t['id']==task['id'] for t in http(url,'/api/tasks?include_closed=true')))
        goal={'task':{'title':title,'column':target_col,'is_active':False,'tags':['smoke']}}
        result=http(url,'/internal/verify','POST',goal,verifier_key=key)
        record('verifier detects exact goal state',result['success'])
        state=http(url,'/internal/state',verifier_key=key)
        record('audit log includes actions',any(e['action']=='close_task' for e in state['events']))
        http(url,f'/api/tasks/{task["id"]}/reopen','POST')
        record('reopening restores visibility',any(t['id']==task['id'] for t in http(url,'/api/tasks')))
    finally:
        try:http(url,'/internal/reset','POST',verifier_key=key)
        except Exception:pass
    return {'passed':all(x['passed'] for x in checks),'checks':checks,'url':url,'mode':'api'}


def run_gui_smoke(url, key='local-dev-verifier', screenshot=None):
    from playwright.sync_api import sync_playwright,expect
    from .capture import browser_kwargs
    title='TC GUI: lifecycle check'
    http(url,'/internal/reset','POST',verifier_key=key)
    checks=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,**browser_kwargs())
            page=browser.new_page(viewport={'width':1440,'height':950})
            page.goto(url,wait_until='networkidle')
            expect(page.get_by_role('heading',name='Clone Research')).to_be_visible(timeout=10000)
            checks.append({'name':'board renders','passed':True})
            page.locator('#new-task').click()
            page.locator('#field-title').fill(title)
            page.locator('#field-column').select_option(index=1)
            page.get_by_role('button',name='Create task').click()
            expect(page.get_by_role('button',name=f'Open task {title}')).to_be_visible()
            checks.append({'name':'create task using GUI','passed':True})
            page.reload(wait_until='networkidle')
            expect(page.get_by_role('button',name=f'Open task {title}')).to_be_visible()
            checks.append({'name':'persists across reload','passed':True})
            page.get_by_role('button',name=f'Open task {title}').click()
            page.get_by_role('button',name='Close task').click()
            expect(page.get_by_role('button',name=f'Open task {title}')).to_have_count(0)
            checks.append({'name':'close via GUI hides task','passed':True})
            response=http(url,'/internal/verify','POST',{'task':{'title':title,'is_active':False}},verifier_key=key)
            checks.append({'name':'GUI task closure verified by DB', 'passed':response['success']})
            if screenshot:
                Path(screenshot).parent.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(screenshot),full_page=True)
            browser.close()
    finally:
        http(url,'/internal/reset','POST',verifier_key=key)
    return {'passed':all(x['passed'] for x in checks),'checks':checks,'url':url,'mode':'gui'}


def evaluate(url, key='local-dev-verifier', gui=False, screenshot=None):
    result=run_api_smoke(url,key)
    if gui:result['gui']=run_gui_smoke(url,key,screenshot)
    result['passed']=result['passed'] and result.get('gui',{'passed':True})['passed']
    return result
