"""File rows over existing task stores, with database paging and stage history retained."""
from uuid import UUID

from django.db import connection
from django.core.exceptions import EmptyResultSet
from django.db.models import Case, CharField, F, Q, Value, When, Window
from django.db.models.functions import Cast, Coalesce, Concat, Replace, RowNumber

from common.capabilities import Capability, has_capability
from ingestion.models import ProcessingJob
from .processing_center import SEMANTIC_STATUS, page_number, task_querysets, task_rows
from .processing_outcomes import workspace_status


def stage_query(rows, source):
    ordinary = source == 'processing_job'
    assets = ['asset__source_asset_id', 'asset_id']
    if ordinary: assets += ['upload_item__asset__source_asset_id', 'upload_item__asset_id']
    asset = Coalesce(*[Cast(field, CharField()) for field in assets])
    has_asset = Q(asset_id__isnull=False) | Q(upload_item__asset_id__isnull=False) if ordinary else Q(asset_id__isnull=False)
    group = Case(When(has_asset,
        then=Concat(Value('file:'), Replace(asset, Value('-'), Value('')))),
        default=Concat(Value(f'task:{source}:'), Replace(Cast('pk', CharField()), Value('-'), Value(''))), output_field=CharField())
    # Keep the constant stage distinct from task_kind: Django's window-filter
    # projection deduplicates identical Value expressions and drops one alias.
    stage = Case(When(stats__operation='outline_rebuild', then=Value('outline_rebuild')), When(stats__operation='concept_alignment', then=Value('concept_alignment')), default=F('job_type'), output_field=CharField()) if ordinary else Cast(Value('semantic_index'), output_field=CharField())
    normalized = workspace_status() if ordinary else Case(*[When(status=old, then=Value(new)) for old,new in SEMANTIC_STATUS.items()], output_field=CharField())
    return rows.order_by().annotate(file_key=group, stage_key=stage,
        task_kind=F('job_type') if ordinary else Value('semantic_index', output_field=CharField()), task_state=normalized,
        store=Value(source, output_field=CharField()), task_pk=Cast('pk', CharField()), task_created=F('created_at'),
    ).annotate(stage_rank=Window(expression=RowNumber(), partition_by=[F('file_key'), F('stage_key')], order_by=[F('created_at').desc(),F('pk').desc()])).filter(Q(stage_rank=1) | Q(task_state__in=['pending','running','paused'])).values('file_key','stage_key','task_kind','task_state','store','task_pk','task_created')


def file_union(jobs, semantic):
    return stage_query(jobs, 'processing_job').union(stage_query(semantic, 'semantic_index_job'), all=True)


def processing_file_page(params, actor):
    jobs, semantic, kind, status = task_querysets(params, actor)
    size, requested = page_number(params.get('page_size'),20,100), page_number(params.get('page'))
    union = file_union(jobs, semantic)
    try:
        sql, args = union.query.sql_with_params()
    except EmptyResultSet:
        counts = {state:0 for state in ProcessingJob.Status.values}
        return {'results':[],'files':[],'group_by':'file','count':0,'page':1,'pages':1,'page_size':size,
            'counts':counts,'total_counts':counts,'total':0,'can_manage':has_capability(actor,Capability.RETRY_JOBS)}
    # The two stores can both contain the same stage. Prefer the latest actual
    # record across them, keeping every in-flight/paused attempt visible.
    # Older finished attempts remain accessible in the task history.
    ranked = f'SELECT stage_rows.*, ROW_NUMBER() OVER (PARTITION BY file_key, stage_key ORDER BY task_created DESC, store DESC, task_pk DESC) AS combined_rank FROM ({sql}) stage_rows'
    latest = f'SELECT * FROM ({ranked}) ranked WHERE combined_rank = 1 OR task_state IN (%s, %s, %s)'
    args = [*args, 'pending', 'running', 'paused']
    predicate, kind_args = ('task_kind = %s', [kind]) if kind else ('1 = 1', [])
    states = ProcessingJob.Status.values
    aggregates = ', '.join(f'MAX(CASE WHEN task_state = %s AND {predicate} THEN 1 ELSE 0 END) AS "{state}"' for state in states)
    aggregate_args = [value for state in states for value in [state, *kind_args]]
    grouped = f'SELECT file_key, MAX(task_created) AS submitted_at, {aggregates} FROM ({latest}) stage_rows GROUP BY file_key HAVING MAX(CASE WHEN {predicate} THEN 1 ELSE 0 END) = 1'
    grouped_args = [*aggregate_args, *args, *kind_args]
    # All dynamic values are bound parameters. SQL identifiers come only from
    # fixed model status values; no client text enters the SQL structure.
    totals_sql = ', '.join(f'COALESCE(SUM("{state}"), 0)' for state in states)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*), {totals_sql} FROM ({grouped}) file_rows', grouped_args)
        totals = cursor.fetchone()
        counts = dict(zip(states, totals[1:]))
        count = counts[status] if status else totals[0]
        pages = max(1,(count+size-1)//size); page = min(requested,pages)
        where = f'WHERE "{status}" = 1' if status else ''
        cursor.execute(f'SELECT file_key FROM ({grouped}) file_rows {where} ORDER BY submitted_at DESC, file_key DESC LIMIT %s OFFSET %s', [*grouped_args,size,(page-1)*size])
        keys = [row[0] for row in cursor.fetchall()]
        refs = []
        stage_counts = {}
        if keys:
            bounded = f'SELECT stage_rows.*, COUNT(*) OVER (PARTITION BY file_key) AS stage_count, ROW_NUMBER() OVER (PARTITION BY file_key ORDER BY task_created DESC, store DESC, task_pk DESC) AS file_rank FROM ({latest}) stage_rows WHERE file_key IN ({", ".join(["%s"]*len(keys))})'
            # ponytail: bound detail hydration to 20 records per file; the existing
            # paginated task history exposes every remaining attempt.
            cursor.execute(f'SELECT file_key, stage_key, store, task_pk, stage_count FROM ({bounded}) bounded WHERE file_rank <= 20 ORDER BY task_created DESC, store DESC, task_pk DESC', [*args,*keys])
            for file_key,stage,source,identifier,stage_count in cursor.fetchall():
                refs.append({'file_key':file_key,'stage_key':stage,'source':source,'id':str(UUID(identifier))})
                stage_counts[file_key] = stage_count
    rendered = task_rows(refs, actor, workspace=True)
    groups = {key:[] for key in keys}
    for ref in refs:
        row = rendered.get((ref['source'],ref['id']))
        if row: groups[ref['file_key']].append(row)
    order = {'ocr':0,'text_extraction':1,'outline_rebuild':2,'page_labels':3,'concept_alignment':4,'discovery_index':5,'semantic_index':6}
    files = []
    for key in keys:
        rows = groups[key]
        if not rows: continue
        headline = rows[0]
        rows.sort(key=lambda row:(order.get(row['operation'] or row['job_type'],10),row['created_at']))
        files.append({'key':key,'title':headline['title'],'edition_label':headline['edition_label'],
            'filename':headline['file']['filename'],'cover_url':headline['cover_url'],'submitted_at':headline['created_at'],
            'stages':rows,'stage_count':stage_counts[key],'has_file':key.startswith('file:')})
    return {'results':[row for item in files for row in item['stages']],'files':files,'group_by':'file',
        'count':count,'page':page,'pages':pages,'page_size':size,'counts':counts,'total_counts':counts,'total':totals[0],
        'can_manage':has_capability(actor,Capability.RETRY_JOBS)}
