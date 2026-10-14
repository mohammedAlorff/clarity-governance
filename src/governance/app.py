"""Single-user local review application. Run with uvicorn on loopback."""

import csv
import io
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import run_inspection
from .contracts import RunLimits
from .privacy import privacy_report
from .providers import create_client, model_settings
from .quality import summarize_results, validate_rule
from .readiness import inspection_readiness
from .source import DemoSource, MySQLSource, result_policies
from .store import Conflict, Store

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / 'static'
load_dotenv(ROOT / '.env.local')
load_dotenv(ROOT / '.env')


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ConnectionBody(Body):
    mode: Literal['demo', 'mysql']


class LimitsBody(Body):
    max_calls: int = Field(default=40, ge=1, le=500)
    max_steps: int = Field(default=8, ge=1, le=32)
    max_seconds: float = Field(default=60.0, gt=0, le=600, allow_inf_nan=False)
    max_tokens: int = Field(default=16000, ge=1, le=200000)
    max_output_tokens: int = Field(default=3000, ge=1, le=16000)
    max_retries: int = Field(default=1, ge=0, le=3)


class InspectionBody(Body):
    mode: Literal['demo', 'agent', 'fixed']
    limits: LimitsBody = Field(default_factory=LimitsBody)


class ReviewBody(Body):
    action: Literal['approve', 'reject', 'clarify', 'edit']
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default='', max_length=2000)
    changes: dict[str, Any] | None = None
    review_seconds: float | None = Field(default=None, ge=0, le=86400, allow_inf_nan=False)


def validate_proposal(proposal, schema):
    if proposal.get('kind') not in ('rule', 'description'):
        raise ValueError('Proposal kind must be rule or description.')
    target = proposal.get('target', {})
    targets = {(t['name'], c['name']) for t in schema['tables'] for c in t['columns']}
    if (target.get('table'), target.get('column')) not in targets:
        raise ValueError('Proposal target is outside the selected schema.')
    for field in ('title', 'description'):
        value = proposal.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise ValueError(f'{field.capitalize()} must contain 1–4000 characters.')
    for field in ('evidence', 'assumptions'):
        value = proposal.get(field, [])
        if (
            not isinstance(value, list)
            or len(value) > 20
            or any(not isinstance(v, str) or len(v) > 2000 for v in value)
        ):
            raise ValueError(f'{field.capitalize()} must be a bounded list of text.')
    if proposal['kind'] == 'rule':
        rule = validate_rule(proposal.get('rule'), schema)
        if rule['target'] != target or rule['metric_id'] == 'profile':
            raise ValueError('An executable rule must match the proposal target.')
        proposal['rule'] = rule
    elif proposal.get('rule') is not None:
        raise ValueError('A description cannot contain an executable rule.')
    return proposal


def create_app(db_path=None):
    app = FastAPI(title='Clarity — Data Governance', version='0.1.0')
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver']
    )
    store = Store(db_path or os.getenv('GOVERNANCE_DB', str(ROOT / 'data' / 'governance.db')))
    lock = RLock()
    runtime = {'source': None, 'scope': None, 'mode': None, 'schema': None}
    previous = store.latest_scope()
    if previous:
        runtime.update(
            source=DemoSource() if previous['mode'] == 'demo' else None,
            scope=previous['id'],
            mode=previous['mode'],
            schema=json.loads(previous['schema_json']),
        )
    app.state.store = store
    app.state.runtime = runtime

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        if request.method == 'POST':
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse(
                    {'detail': 'Cross-origin write requests are not allowed.'}, status_code=403
                )
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse(
                    {'detail': 'Cross-site write requests are not allowed.'}, status_code=403
                )
            if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'detail': 'Use application/json.'}, status_code=415)
            body = await request.body()
            if len(body) > 65536:
                return JSONResponse({'detail': 'Request is too large.'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'"
        )
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def value_handler(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=422)

    @app.exception_handler(KeyError)
    async def key_handler(request, exc):
        return JSONResponse({'detail': 'Requested record was not found.'}, status_code=404)

    def require_source():
        if runtime['source'] is None:
            raise HTTPException(409, 'Connect a test source first.')
        return runtime['source']

    def annotate_report(report, proposals):
        current = {
            (p['id'], p['version'])
            for p in proposals
            if p['kind'] == 'rule' and p['status'] == 'approved'
        }
        measured = {(r['proposal_id'], r['version']) for r in report['results']}
        return {**report, 'outdated': current != measured}

    def get_state():
        scope = runtime['scope']
        schema = runtime['schema']
        proposals = store.proposals(scope) if scope else []
        reports = store.records(scope, 'report') if scope else []
        inspections = store.records(scope, 'inspection') if scope else []
        try:
            selected = model_settings()
            settings = {
                'provider': selected['provider'],
                'model': selected['model'],
                'model_configured': selected['configured'],
                'configuration_error': None,
            }
        except ValueError as exc:
            settings = {
                'provider': 'unconfigured',
                'model': '',
                'model_configured': False,
                'configuration_error': str(exc),
            }
        return {
            'source': {
                'mode': runtime['mode'],
                'name': schema['name'] if schema else 'No source selected',
                'connected': runtime['source'] is not None,
            },
            'schema': schema,
            'proposals': proposals,
            'inspections': inspections,
            'report': annotate_report(reports[0], proposals) if reports else None,
            'settings': settings,
            'privacy': privacy_report(inspections, settings['provider']),
            'evaluation': {
                'status': 'pending',
                'message': 'Live evaluation is pending: configure MySQL and a model, review reference answers, run the development pilot, freeze targets, then run at least three uncached trials per final case. Synthetic demo results are not final evidence.',
            },
            'counts': {
                'tables': len(schema['tables']) if schema else 0,
                'columns': sum(len(t['columns']) for t in schema['tables']) if schema else 0,
                'pending': sum(p['status'] in ('draft', 'needs_clarification') for p in proposals),
                'approved': sum(p['status'] == 'approved' for p in proposals),
            },
        }

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    @app.get('/api/state')
    def state():
        with lock:
            return get_state()

    @app.post('/api/connect')
    def connect(body: ConnectionBody):
        with lock:
            source = None
            try:
                source = DemoSource() if body.mode == 'demo' else MySQLSource.from_env()
                schema = source.get_schema()
            except Exception:
                if source:
                    source.close()
                raise HTTPException(
                    422,
                    'Could not connect. Check the server environment, selected MySQL schema, read-only grants, and connection settings.',
                ) from None
            if runtime['source']:
                runtime['source'].close()
            runtime.update(
                source=source,
                schema=schema,
                mode=body.mode,
                scope=store.new_scope(body.mode, schema['name'], schema),
            )
            return get_state()

    @app.post('/api/inspect/preflight')
    def preflight(body: InspectionBody):
        with lock:
            return inspection_readiness(
                runtime['schema'],
                runtime['mode'],
                body.mode,
                RunLimits(**body.limits.model_dump()),
                source_connected=runtime['source'] is not None,
            )

    @app.post('/api/inspect')
    def inspect(body: InspectionBody):
        with lock:
            source = require_source()
            if body.mode == 'demo' and runtime['mode'] != 'demo':
                raise HTTPException(
                    422, 'Synthetic inspection is available only for the demo source.'
                )
            client = create_client() if body.mode != 'demo' else None
            result = run_inspection(
                source, client=client, mode=body.mode, limits=RunLimits(**body.limits.model_dump())
            )
            valid = []
            for candidate in result.get('proposals', []):
                try:
                    valid.append(validate_proposal(candidate, runtime['schema']))
                except (ValueError, TypeError, KeyError, AttributeError):
                    result.setdefault('validation_errors', []).append(
                        'An invalid proposal was withheld.'
                    )
            record = store.add_record(
                runtime['scope'], 'inspection', {**result, 'proposals': valid, 'mode': body.mode}
            )
            for proposal in valid:
                store.add_proposal(runtime['scope'], {**proposal, 'inspection_id': record['id']})
            return get_state()

    @app.post('/api/proposals/{pid}/review')
    def review(pid: str, body: ReviewBody):
        with lock:
            require_source()
            proposal = store.get_proposal(pid)
            if proposal['scope'] != runtime['scope']:
                raise Conflict('This proposal belongs to a different source scope.')
            if body.action == 'edit':
                if not body.changes:
                    raise ValueError('Provide a change to create a new draft.')
                validate_proposal({**proposal, **body.changes}, runtime['schema'])
            if body.action == 'approve':
                validate_proposal(proposal, runtime['schema'])
            store.review(
                pid, body.action, body.reviewer, body.note, body.changes, body.review_seconds
            )
            return get_state()

    @app.post('/api/checks/run')
    def run_checks(body: Body):
        with lock:
            source = require_source()
            rules = store.approved_rules(runtime['scope'])
            if not rules:
                raise HTTPException(409, 'Approve at least one rule before running checks.')
            results = []
            for proposal in rules:
                rule = proposal['rule']
                try:
                    rule = validate_rule(rule, source.get_schema())
                    result = source.run_metric(
                        rule['metric_id'], rule['target'], rule['parameters']
                    )
                except Exception:
                    dimension = {
                        'completeness': 'completeness',
                        'uniqueness': 'uniqueness',
                        'column_compare': 'consistency',
                        'referential': 'consistency',
                    }.get(rule['metric_id'], 'validity')
                    result = {
                        'metric_id': rule['metric_id'],
                        'target': proposal['target'],
                        'dimension': dimension,
                        'status': 'failed',
                        'eligible': 0,
                        'passing': 0,
                        'violations': 0,
                        'reason': 'The read-only check could not complete. Check schema availability and query limits.',
                        'violation_ids': [],
                        **result_policies(rule['metric_id']),
                    }
                results.append(
                    {
                        **result,
                        'title': proposal['title'],
                        'proposal_id': proposal['id'],
                        'version': proposal['version'],
                        'parameters': rule['parameters'],
                        'reviewer': proposal['reviewer'],
                        'approved_at': proposal['reviewed_at'],
                    }
                )
            proposals = store.proposals(runtime['scope'])
            inspections = store.records(runtime['scope'], 'inspection')
            schema = runtime['schema']
            selected_targets = {
                t['name'] + '.' + c['name'] for t in schema['tables'] for c in t['columns']
            }
            profiled_targets = {
                target
                for inspection in inspections
                for target in inspection.get('inspected_targets', [])
                if isinstance(target, str) and target in selected_targets
            }
            report = {
                'source': {'name': schema['name'], 'mode': runtime['mode']},
                'results': results,
                'summary': summarize_results(results),
                'unresolved': sum(
                    p['status'] in ('draft', 'needs_clarification') for p in proposals
                ),
                'inspection_ids': [i['id'] for i in inspections],
                'selected_columns': sum(len(t['columns']) for t in schema['tables']),
                'profiled_columns': len(profiled_targets),
                'models': [
                    {'provider': i.get('provider'), 'model': i.get('model'), 'mode': i.get('mode')}
                    for i in inspections
                ],
                'note': 'Scores apply only to the listed approved rules. They do not certify all data quality issues have been found.',
            }
            store.add_record(runtime['scope'], 'report', report)
            return get_state()

    def get_dictionary():
        if runtime['schema'] is None:
            raise HTTPException(409, 'Connect a test source first.')
        proposals = store.proposals(runtime['scope'])
        columns = []
        for table in runtime['schema']['tables']:
            for column in table['columns']:
                descriptions = [
                    p
                    for p in proposals
                    if p['kind'] == 'description'
                    and p['target'] == {'table': table['name'], 'column': column['name']}
                ]
                approved = [p for p in descriptions if p['status'] == 'approved']
                selected = approved[-1] if approved else descriptions[-1] if descriptions else None
                columns.append(
                    {
                        'table': table['name'],
                        'column': column['name'],
                        'data_type': column['data_type'],
                        'nullable': column['nullable'],
                        'key': column.get('key', ''),
                        'description': selected['description'] if selected else '',
                        'status': selected['status'] if selected else 'not_documented',
                        'evidence': selected['evidence'] if selected else [],
                        'version': selected['version'] if selected else None,
                    }
                )
        return {'source': runtime['schema']['name'], 'columns': columns}

    @app.get('/api/dictionary')
    def dictionary():
        with lock:
            return get_dictionary()

    @app.get('/api/export/dictionary')
    def export_dictionary():
        with lock:
            data = get_dictionary()
            buffer = io.StringIO(newline='')
            keys = [
                'table',
                'column',
                'data_type',
                'nullable',
                'key',
                'description',
                'status',
                'evidence',
                'version',
            ]
            writer = csv.DictWriter(buffer, fieldnames=keys)
            writer.writeheader()
            for row in data['columns']:
                safe = {}
                for key, value in row.items():
                    text = (
                        json.dumps(value)
                        if isinstance(value, list)
                        else str(value if value is not None else '')
                    )
                    safe[key] = (
                        "'" + text
                        if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n'))
                        else text
                    )
                writer.writerow(safe)
            return Response(
                buffer.getvalue(),
                media_type='text/csv',
                headers={'Content-Disposition': 'attachment; filename="data-dictionary.csv"'},
            )

    @app.get('/api/export/report')
    def export_report():
        with lock:
            reports = store.records(runtime['scope'], 'report') if runtime['scope'] else []
            if not reports:
                raise HTTPException(404, 'Run approved checks to create a report first.')
            report = annotate_report(reports[0], store.proposals(runtime['scope']))
            return Response(
                json.dumps(report, indent=2),
                media_type='application/json',
                headers={'Content-Disposition': 'attachment; filename="quality-report.json"'},
            )

    @app.get('/api/export/privacy')
    def export_privacy():
        with lock:
            return Response(
                json.dumps(get_state()['privacy'], indent=2),
                media_type='application/json',
                headers={'Content-Disposition': 'attachment; filename="privacy-report.json"'},
            )

    if STATIC.exists():
        app.mount('/static', StaticFiles(directory=STATIC), name='static')

    @app.get('/')
    def home():
        return FileResponse(STATIC / 'index.html')

    return app


app = create_app()
