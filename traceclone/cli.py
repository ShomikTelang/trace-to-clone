"""Command-line orchestrator for the first Trace-to-Clone milestone."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .generate import ROOT, generate


def build_parser():
    parser=argparse.ArgumentParser(prog='traceclone',description='Evidence-grounded Kanban trace-to-clone prototype')
    sub=parser.add_subparsers(dest='command',required=True)
    g=sub.add_parser('generate',help='Generate runnable Kanban clone from a reviewed spec')
    g.add_argument('--spec',default=str(ROOT/'specs/kanboard_mvp.json'))
    g.add_argument('--out',default=str(ROOT/'generated/kanboard-clone'))
    g.add_argument('--force',action='store_true')
    r=sub.add_parser('record',help='Collect reference snapshots/Playwright traces using a workflow or guided checkpoints')
    r.add_argument('--url',default='http://localhost:8081')
    r.add_argument('--out',default=str(ROOT/'artifacts/reference_trace'))
    r.add_argument('--workflow',help='JSON action workflow; omitted means guided manual mode')
    r.add_argument('--storage-state',help='Saved authentication state from login command')
    r.add_argument('--headed',action='store_true',help='Show browser; required for guided mode')
    l=sub.add_parser('login',help='Authenticate in visible browser; save local Playwright storage state')
    l.add_argument('--url',default='http://localhost:8081')
    l.add_argument('--out',default=str(ROOT/'reference/storage-state.json'))
    i=sub.add_parser('infer',help='Produce an evidence-based observation draft from a trace')
    i.add_argument('--trace',default=str(ROOT/'artifacts/reference_trace/trace.json'))
    i.add_argument('--out',default=str(ROOT/'artifacts/inference_draft.json'))
    i.add_argument('--llm',action='store_true',help='Include OPTIONAL LLM-generated unverified spec proposal (requires API key)')
    i.add_argument('--model',default='gpt-4.1-mini')
    d=sub.add_parser('demo',help='Generate clone if needed and start local web server')
    d.add_argument('--spec',default=str(ROOT/'specs/kanboard_mvp.json'))
    d.add_argument('--out',default=str(ROOT/'generated/kanboard-clone'))
    d.add_argument('--port',type=int,default=8000)
    e=sub.add_parser('evaluate',help='Test a running clone, including privileged-state verification')
    e.add_argument('--url',default='http://localhost:8000')
    e.add_argument('--key',default=os.environ.get('VERIFIER_KEY','local-dev-verifier'))
    e.add_argument('--gui',action='store_true',help='Also test using Chromium GUI')
    e.add_argument('--screenshot')
    e.add_argument('--out',help='Save evaluation result JSON')
    return parser


def main(argv=None):
    args=build_parser().parse_args(argv)
    if args.command=='generate':
        print('Generated',generate(args.spec,args.out,args.force))
    elif args.command=='demo':
        target=Path(args.out)
        if not target.exists():print('Generated',generate(args.spec,args.out))
        print(f'Starting the synthetic clone at http://localhost:{args.port} (Ctrl+C to stop)',flush=True)
        env=os.environ.copy();env['PORT']=str(args.port)
        subprocess.run([sys.executable,str(target/'server.py')],env=env,check=True)
    elif args.command=='login':
        from .capture import login
        login(args.url,args.out)
    elif args.command=='record':
        from .capture import capture
        capture(args.url,args.out,workflow=args.workflow,headed=args.headed,storage_state=args.storage_state)
    elif args.command=='infer':
        from .infer import infer
        result=infer(args.trace,args.out,args.llm,args.model)
        print('Wrote',args.out,'(status:',result['status']+')')
    elif args.command=='evaluate':
        from .evaluate import evaluate
        result=evaluate(args.url,args.key,args.gui,args.screenshot)
        rendered=json.dumps(result,indent=2)
        print(rendered)
        if args.out:
            Path(args.out).parent.mkdir(parents=True,exist_ok=True)
            Path(args.out).write_text(rendered+'\n')
        if not result['passed']:sys.exit(1)

if __name__=='__main__':main()
