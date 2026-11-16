"""Playwright evidence collector for controlled reference applications.

Two modes:
  scripted: execute a JSON workflow to obtain reproducible before/after traces;
  guided: a human explores the real site, pressing Enter to capture checkpoints.

No arbitrary credentials or request bodies are logged by default. Captured DOM and
screenshots may still contain private data: run only on a disposable test account.
"""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

CAPTURE_JS = r"""() => {
  const visible = (el) => {const r=el.getBoundingClientRect(); const style=getComputedStyle(el); return r.width>0 && r.height>0 && style.visibility!=='hidden' && style.display!=='none'};
  const els=[...document.querySelectorAll('a,button,input,textarea,select,[role=button],[role=tab],form')].filter(visible).slice(0,250);
  return {
    title: document.title,
    headings: [...document.querySelectorAll('h1,h2,h3')].map(x=>x.innerText.trim()).filter(Boolean).slice(0,35),
    interactive: els.map(el=>{
      const r=el.getBoundingClientRect(), cs=getComputedStyle(el);
      return {tag:el.tagName.toLowerCase(),role:el.getAttribute('role'),type:el.getAttribute('type'),
        id:el.id||null,name:el.getAttribute('name'),label:el.getAttribute('aria-label'),
        placeholder:el.getAttribute('placeholder'),text:(el.innerText||el.textContent||'').trim().slice(0,130),
        href:el.tagName==='A' ? (el.getAttribute('href')||'').slice(0,200) : null,
        box:{x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)},
        styles:{color:cs.color,bg:cs.backgroundColor,fontSize:cs.fontSize,fontWeight:cs.fontWeight,borderRadius:cs.borderRadius}};
    }),
    text:(document.body.innerText||'').slice(0,16000)
  };
}"""
EVENT_JS = r"""(() => {
  const describe=(e,kind)=>{
    const el = e.target && e.target.closest ? e.target.closest('button,a,input,textarea,select,[role=button]') : null;
    if(!el)return;
    const label=el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || (el.innerText||'').trim().slice(0,120);
    const detail={kind,tag:el.tagName.toLowerCase(),id:el.id||null,label:label.slice(0,120),type:el.type||null,url:location.pathname,at:new Date().toISOString()};
    if(kind==='change' && el.type!=='password' && el.type!=='hidden') detail.value=String(el.value||'').slice(0,180);
    window.__tcEmit?.(detail).catch(()=>{});
  };
  window.addEventListener('click',e=>describe(e,'click'),true);
  window.addEventListener('change',e=>describe(e,'change'),true);
})()"""


def browser_kwargs():
    path=os.environ.get('CHROMIUM_PATH')
    return {'executable_path':path} if path else {}


def clean_url(url):
    x=urlsplit(url)
    return f'{x.scheme}://{x.netloc}{x.path}' if x.scheme else x.path


def loc(page, locator):
    if 'css' in locator:return page.locator(locator['css'])
    if 'role' in locator:return page.get_by_role(locator['role'],name=locator.get('name'))
    if 'label' in locator:return page.get_by_label(locator['label'])
    if 'text' in locator:return page.get_by_text(locator['text'],exact=locator.get('exact',True))
    if 'placeholder' in locator:return page.get_by_placeholder(locator['placeholder'])
    if 'testid' in locator:return page.get_by_test_id(locator['testid'])
    raise ValueError(f'unsupported locator {locator}')


def run_action(page, step, base_url):
    kind=step['action']
    if kind=='goto':
        page.goto(urljoin(base_url.rstrip('/')+'/',step.get('url','/')),wait_until='domcontentloaded')
    elif kind=='click':loc(page,step['locator']).click(timeout=12000)
    elif kind=='fill':loc(page,step['locator']).fill(step['value'],timeout=12000)
    elif kind=='select':loc(page,step['locator']).select_option(label=step['value'],timeout=12000)
    elif kind=='check':loc(page,step['locator']).check(timeout=12000)
    elif kind=='press':loc(page,step['locator']).press(step['key'],timeout=12000)
    elif kind=='wait':page.wait_for_timeout(step.get('ms',600))
    else:raise ValueError(f'unsupported action {kind}')


def snapshot(page, directory, index, label):
    name=f'{index:03d}_{re.sub(r"[^a-z0-9_-]", "_",label.lower())[:42]}'
    screenshot=f'{name}.png'
    page.screenshot(path=str(directory/screenshot),full_page=True,timeout=12000)
    data=page.evaluate(CAPTURE_JS)
    html=page.content()
    # Only a bounded DOM sample; binary, login state, cookies and passwords are not intentionally collected.
    html_path=f'{name}.html'
    (directory/html_path).write_text(html[:120000],encoding='utf-8')
    return {**data,'url':clean_url(page.url),'screenshot':screenshot,'html':html_path,'captured_at':time.time()}


def capture(url, output, workflow=None, headed=False, storage_state=None):
    from playwright.sync_api import sync_playwright
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    network=[];browser_events=[];snapshots=[];executions=[]
    flow=json.loads(Path(workflow).read_text()) if workflow else None
    if not flow and not headed:
        raise ValueError('Guided capture needs a visible browser: use --headed')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=not headed,**browser_kwargs())
        options={'viewport':{'width':1440,'height':950},'device_scale_factor':1}
        if storage_state:options['storage_state']=str(storage_state)
        context=browser.new_context(**options)
        context.expose_binding('__tcEmit',lambda _source,payload:browser_events.append(payload))
        context.add_init_script(EVENT_JS)
        context.tracing.start(screenshots=True,snapshots=True,sources=True)
        page=context.new_page()
        page.on('response',lambda response: network.append({'method':response.request.method,'status':response.status,'url':clean_url(response.url),'resource_type':response.request.resource_type}) if len(network)<1000 else None)
        try:
            page.goto(url,wait_until='domcontentloaded',timeout=30000)
            page.wait_for_timeout(400)
            snapshots.append(snapshot(page,output,0,'initial'))
            if flow:
                for i,step in enumerate(flow['steps'],1):
                    started=time.perf_counter()
                    try:
                        run_action(page,step,url)
                        page.wait_for_timeout(step.get('settle_ms',300))
                        executions.append({'index':i,'action':step['action'],'locator':step.get('locator'),'value':'[REDACTED]' if 'password' in str(step.get('locator','')).lower() else step.get('value'),'elapsed_ms':round((time.perf_counter()-started)*1000)})
                        snapshots.append(snapshot(page,output,i,step.get('name',step['action'])))
                    except Exception as e:
                        executions.append({'index':i,'action':step['action'],'error':str(e)})
                        try:snapshots.append(snapshot(page,output,i,'error'))
                        except Exception:pass
                        break
            else:
                print('Guided capture: interact with the reference app in the browser. Each Enter captures a checkpoint; type done to finish.')
                i=1
                while True:
                    try:label=input(f'Checkpoint {i} label (or "done"): ').strip()
                    except EOFError:break
                    if label.lower() in {'done','quit','exit'}:break
                    try:
                        snapshots.append(snapshot(page,output,i,label or f'checkpoint_{i}'))
                        i+=1
                    except Exception as e:print('snapshot failed:',e)
        finally:
            context.tracing.stop(path=str(output/'playwright_trace.zip'))
            (output/'trace.json').write_text(json.dumps({'reference_url':clean_url(url),'mode':'scripted' if flow else 'guided','workflow':flow,'executions':executions,'browser_events':browser_events,'snapshots':snapshots,'network':network},indent=2),encoding='utf-8')
            browser.close()
    print(f'Captured {len(snapshots)} checkpoints in {output}')
    if any('error' in x for x in executions):
        raise RuntimeError('Workflow had a failed action; inspect trace.json and screenshots')
    return output


def login(url, output):
    from playwright.sync_api import sync_playwright
    target=Path(output).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=False,**browser_kwargs())
        context=browser.new_context()
        page=context.new_page()
        page.goto(url,wait_until='domcontentloaded')
        print('Log into your own LOCAL reference test account in the opened browser.')
        input('Press Enter after login is complete to save the browser session locally...')
        context.storage_state(path=str(target))
        browser.close()
    target.chmod(0o600)
    print(f'Saved session state to {target}. This is a sensitive file; do not commit it.')
