import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from traceclone.generate import generate
from traceclone.infer import draft_from_trace

SOURCE = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    dest = generate(str(SOURCE/'specs/kanboard_mvp.json'),str(tmp_path/'instance'))
    monkeypatch.setenv('CLONE_DB_PATH',str(tmp_path/'fixture.sqlite3'))
    monkeypatch.setenv('VERIFIER_KEY','test-secret')
    spec=importlib.util.spec_from_file_location(f'clone_runtime_{id(tmp_path)}',dest/'server.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TestClient(module.app) as c:
        yield c


def header():return {'X-Verifier-Key':'test-secret'}


def test_initial_seed_and_ui(client):
    assert client.get('/health').json()['status']=='ok'
    assert len(client.get('/api/tasks').json())==3
    assert client.get('/').status_code==200
    assert 'Kanban board' in client.get('/').text
    assert client.get('/static/app.js').status_code==200
    assert client.get('/api/spec').json()['columns'][0]['id']=='Backlog'
    assert 'initial_tasks' not in client.get('/api/spec').json()


def test_create_move_close_reopen_and_verify(client):
    r=client.post('/api/tasks',json={'title':'Fix login bug','tags':['auth'],'priority':'P0'})
    assert r.status_code==201
    task=r.json();taskid=task['id']
    assert task['column']=='Backlog'
    r=client.patch(f'/api/tasks/{taskid}',json={'column':'Work in progress','description':'Urgent issue'})
    assert r.status_code==200
    assert r.json()['description']=='Urgent issue'
    assert r.json()['column']=='Work in progress'
    assert client.post(f'/api/tasks/{taskid}/close').json()['is_active'] is False
    assert all(t['id']!=taskid for t in client.get('/api/tasks').json())
    assert any(t['id']==taskid for t in client.get('/api/tasks?include_closed=true').json())
    goal={'task':{'title':'Fix login bug','column':'Work in progress','priority':'P0','tags':['auth'],'is_active':False}}
    assert client.post('/internal/verify',headers=header(),json=goal).json()['success']
    events=client.get('/internal/state',headers=header()).json()['events']
    assert [e['action'] for e in events]==['create_task','update_task','close_task']
    assert client.post(f'/api/tasks/{taskid}/reopen').json()['is_active']
    assert any(t['id']==taskid for t in client.get('/api/tasks').json())


def test_private_api_and_validation(client):
    assert client.get('/internal/state').status_code==403
    assert client.post('/internal/reset',headers={'X-Verifier-Key':'wrong'}).status_code==403
    assert client.post('/internal/verify',headers=header(),json={'task':{}}).status_code==422
    assert client.post('/internal/verify',headers=header(),json={'task':{'magic':'bad'}}).status_code==422
    assert client.post('/api/tasks',json={'title':'  '}).status_code==422
    assert client.post('/api/tasks',json={'title':'bad','column':'Missing'}).status_code==422
    assert client.post('/api/tasks',json={'title':'bad','priority':'P10'}).status_code==422
    assert client.get('/api/tasks/999').status_code==404
    assert client.patch('/api/tasks/999',json={'title':'no'}).status_code==404
    assert client.patch('/api/tasks/1',json={'column':'Bad'}).status_code==422


def test_reset_is_deterministic(client):
    a=client.get('/api/tasks').json()
    client.post('/api/tasks',json={'title':'Temp'})
    client.post('/internal/reset',headers=header())
    b=client.get('/api/tasks').json()
    assert [t['id'] for t in a]==[t['id'] for t in b]
    assert [t['title'] for t in a]==[t['title'] for t in b]
    assert client.get('/internal/state',headers=header()).json()['events']==[]


def test_generator_reads_spec_instead_of_hardcoding(tmp_path):
    spec=json.loads((SOURCE/'specs/kanboard_mvp.json').read_text())
    spec['title']='Research Sandbox B'
    spec['columns']=[{'id':'Inbox','label':'Inbox'},{'id':'Completed','label':'Completed'}]
    spec['default_column']='Inbox'
    spec['initial_tasks']=[]
    input_file=tmp_path/'alternate.json';input_file.write_text(json.dumps(spec))
    dest=generate(str(input_file),str(tmp_path/'alternate'))
    result=json.loads((dest/'spec.json').read_text())
    assert result['title']=='Research Sandbox B'
    assert len(result['columns'])==2
    assert (dest/'static/app.js').exists()
    with pytest.raises(FileExistsError):generate(str(input_file),str(dest))


def test_trace_inference_does_not_fabricate_backend():
    trace={'reference_url':'http://localhost:8081','snapshots':[{'url':'http://localhost:8081/board','title':'Demo Board','headings':['My board'],'screenshot':'001.png','interactive':[{'tag':'button','text':'Create task'},{'tag':'input','id':'task-name','placeholder':'Title','type':'text'}]}], 'browser_events':[{'kind':'click'}],'executions':[]}
    draft=draft_from_trace(trace)
    assert draft['observed_pages'][0]['controls'][0]['label']=='Create task'
    assert draft['observed_pages'][0]['fields'][0]['label']=='Title'
    assert 'persistent state schema' in draft['unknowns']
    assert draft['status']=='observation_draft_only'
