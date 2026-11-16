"""Evidence-grounded inference draft from browser traces.

Default: deterministic observation extraction (does not invent backend behavior).
--llm: optional model-aided draft; must be reviewed before using it as a spec.
"""
from collections import Counter
from pathlib import Path
import json
import os


def draft_from_trace(trace):
    pages=[]
    keys=set()
    for snapshot in trace.get('snapshots',[]):
        fields=[]
        actions=[]
        for node in snapshot.get('interactive',[]):
            key=node.get('label') or node.get('text') or node.get('placeholder') or node.get('id')
            if not key:continue
            kind=node.get('tag')
            if kind in {'input','textarea','select'}:
                fields.append({'label':key,'type':node.get('type') or kind,'id':node.get('id'),'observed':True})
            elif kind in {'button','a'} or node.get('role')=='button':
                actions.append({'label':key,'kind':kind,'observed':True})
            keys.add(key)
        pages.append({'url':snapshot.get('url'),'title':snapshot.get('title'),'headings':snapshot.get('headings',[]),'fields':fields[:50],'controls':actions[:80],'screenshot':snapshot.get('screenshot')})
    event_kinds=Counter(x.get('kind') for x in trace.get('browser_events',[]))
    return {
        'schema_version':'0.1',
        'status':'observation_draft_only',
        'source':trace.get('reference_url'),
        'observed_pages':pages,
        'observed_events':dict(event_kinds),
        'scripted_actions':trace.get('executions',[]),
        'unique_control_labels':len(keys),
        'unknowns':['persistent state schema','server-side side effects','unobserved transitions','permissions','hidden business rules'],
        'next_step':'Review this draft and author/update a bounded executable specification; optional --llm can propose one.'
    }


def llm_propose(trace, observations, model):
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError('pip install -e ".[llm]" first') from e
    if not os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('OPENAI_API_KEY environment variable required for --llm')
    # Avoid leaking full DOM, cookies, credentials or image data to an external model.
    cleaned={'reference_url':trace.get('reference_url'),'observations':observations}
    prompt='''You infer a bounded application specification ONLY from observed browser evidence.
Return a JSON object with keys: proposed_spec, evidence_map, uncertainties, suggested_tests.
proposed_spec should target a Kanban-like task app with schema_version, app_id, title, subtitle, columns (id,label), priorities, default_column, default_priority, fields, actions, initial_tasks.
Do NOT fabricate workflows or backend behavior. If unknown, put it under uncertainties and mark as an assumption in evidence_map. Do not include secrets. Return strictly valid JSON.'''
    client=OpenAI()
    result=client.chat.completions.create(model=model,messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(cleaned)[:65000]}],response_format={'type':'json_object'})
    return json.loads(result.choices[0].message.content)


def infer(trace_file, output, llm=False, model='gpt-4.1-mini'):
    trace=json.loads(Path(trace_file).read_text())
    draft=draft_from_trace(trace)
    if llm:
        proposed=llm_propose(trace,draft,model)
        draft['llm_proposal']=proposed
        draft['status']='llm_proposal_unverified'
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(draft,indent=2)+'\n')
    return draft
