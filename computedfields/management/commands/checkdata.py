import sys
from time import time
from argparse import FileType
from json import dumps
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, DatabaseError

from computedfields.helper import modelname, slice_iterator
from computedfields.settings import settings
from computedfields.models import active_resolver
from ._helpers import tqdm, HAS_TQDM, retrieve_computed_models


# abort search for tainted
TAINTED_MAXLENGTH = 10


class Command(BaseCommand):
    help = 'Check computed field values.'
    silent = False
    skip_tainted = False

    def add_arguments(self, parser):
        parser.add_argument(
            'args', metavar='app_label[.ModelName]', nargs='*',
            help='Check computed field values on specified app_label or app_label.ModelName.',
        )
        parser.add_argument(
            '-p', '--progress',
            action='store_true',
            help='Show check progress.',
        )
        parser.add_argument(
            '-q', '--querysize',
            default=settings.COMPUTEDFIELDS_QUERYSIZE,
            type=int,
            help='Set queryset size, default: 2000 or value from settings.py.'
        )
        parser.add_argument(
            '--json',
            type=FileType('w'),
            default=None,
            help='Write desync data as JSONL.',
        )
        parser.add_argument(
            '--silent',
            action='store_true',
            help='Silence normal command output.',
        )
        parser.add_argument(
            '--skip-tainted',
            action='store_true',
            help='Skip tainted deep search.',
        )
    
    def eprint(self, *args, **kwargs):
        if not self.silent:
            print(*args, file=sys.stderr, **kwargs)

    def handle(self, *app_labels, **options):
        start_time = time()
        progress = options['progress']
        size = options['querysize']
        json_out = options['json']
        self.silent = options['silent']
        self.skip_tainted = options['skip_tainted']
        if progress and not HAS_TQDM:
            raise CommandError('Package "tqdm" needed for the progressbar.')
        has_desync = self.action_check(retrieve_computed_models(app_labels), progress, size, json_out)
        end_time = time()
        duration = int(end_time - start_time)
        self.eprint(f'\nTotal check time: {timedelta(seconds=duration)}')
        sys.exit(1 if has_desync else 0)
    
    @transaction.atomic
    def action_check(self, models, progress, size, json_out):
        has_desync = False
        for model in models:
            qs = model._base_manager.all()
            amount = qs.count()
            fields = set(active_resolver.computed_models[model].keys())
            qsize = active_resolver.get_querysize(model, fields, size)
            self.eprint(f'- {self.style.MIGRATE_LABEL(modelname(model))}')
            self.eprint(f'  Fields: {", ".join(fields)}')
            self.eprint(f'  Records: {amount}')
            if not amount:
                continue

            # apply select/prefetch rules
            select = active_resolver.get_select_related(model, fields)
            prefetch = active_resolver.get_prefetch_related(model, fields)
            if select:
                qs = qs.select_related(*select)
            if prefetch:
                qs = qs.prefetch_related(*prefetch)

            # check sync state
            desync = []
            if progress:
                with tqdm(total=amount, desc='  Check', unit=' rec', disable=self.silent) as bar:
                    for obj in slice_iterator(qs, qsize):
                        if not check_instance(model, fields, obj):
                            desync.append(obj.pk)
                        bar.update(1)
            else:
                for obj in slice_iterator(qs, qsize):
                    if not check_instance(model, fields, obj):
                        desync.append(obj.pk)

            if not desync:
                self.eprint(self.style.SUCCESS (f'  Desync: 0 records'))
            else:
                has_desync = True
                self.eprint(self.style.WARNING(f'  Desync: {len(desync)} records ({percent(len(desync), amount)})'))
                if not self.silent and not self.skip_tainted:
                    mode, tainted = try_tainted(qs, desync, amount)
                    if tainted:
                        self.eprint(self.style.NOTICE(f'  Tainted dependants:'))
                        for level, submodel, fields, count in tainted:
                            records = ''
                            if mode == 'concrete':
                                records = '~'
                            elif mode == 'approx':
                                records = '>>'
                            records += f'{count} records' if count != -1 else 'records unknown'
                            self.eprint(self.style.NOTICE(
                                '    ' * level +
                                f'└─ {modelname(submodel)}: {", ".join(fields)} ({records})'
                            ))
                        if len(tainted) >= TAINTED_MAXLENGTH:
                            self.eprint(self.style.NOTICE('  (listing shortened...)'))
                if json_out:
                    json_out.write(dumps({'model': modelname(model), 'desync': desync}))
        return has_desync


def percent(part, total):
    return f'{round(100.0 * part / total, 2)}%'


def check_instance(model, fields, obj):
    for comp_field in fields:
        new_value = active_resolver._compute(obj, model, comp_field)
        if new_value != getattr(obj, comp_field):
            return False
    return True


def try_tainted(qs, desync, amount):
    """
    Try to reveal tainted follow-up cf records opportunistically.
    Since this is only to give an idea of maybe wrong records in the database,
    we are not interested in exact numbers. We only do an exact calculation
    with DFS on the first 1000 desync records. For bigger desyncs the numbers
    get later marked with '>>' to indicate, that the tainted records are much higher.
    If we encounter a database error from the descent, we only return
    the tainted follow-up field dependencies.

    The tainted listing gets shortened to TAINTED_MAXLENGTH in any case to not
    make the output unreadable. It also ensures, that we dont spam tons of records
    for recursive models.
    """
    mode = 'concrete'
    if len(desync) == amount:
        _qs = qs
    else:
        if len(desync) > 1000:
            mode = 'approx'
            desync = desync[:1000]
        _qs = qs.filter(pk__in=desync)
    tainted = []
    try:
        with transaction.atomic():
            tainted = reveal_tainted(_qs)
    except DatabaseError:
        tainted = reveal_modeldeps(qs)
        mode = 'deps'
    return mode, tainted


def reveal_tainted(qs):
    """
    Full DFS taint counter used up to 1000 records.
    """
    tainted = []
    updates = active_resolver._querysets_for_update(qs.model, qs).values()
    for queryset, fields in updates:
        bulk_counter(queryset, fields, level=1, store=tainted)
        if len(tainted) >= TAINTED_MAXLENGTH:
            break
    return tainted


def bulk_counter(qs, f, level, store):
    if len(store) >= TAINTED_MAXLENGTH:
        return
    if qs.exists():
        pks = set(qs.values_list('pk', flat=True).iterator())
        store.append((level, qs.model, f, len(pks)))
        updates = active_resolver._querysets_for_update(qs.model, qs.values('pk'), f).values()
        for queryset, fields in updates:
            bulk_counter(queryset, fields, level=level+1, store=store)


def reveal_modeldeps(qs):
    """
    DFS model deps aggregator without record count.
    """
    tainted = []
    updates = active_resolver._querysets_for_update(qs.model, qs).values()
    for queryset, fields in updates:
        bulk_deps(queryset, fields, level=1, store=tainted)
        if len(tainted) >= TAINTED_MAXLENGTH:
            break
    return tainted


def bulk_deps(qs, f, level, store):
    if len(store) >= TAINTED_MAXLENGTH:
        return
    store.append((level, qs.model, f, -1))
    updates = active_resolver._querysets_for_update(qs.model, qs, f).values()
    for queryset, fields in updates:
        bulk_deps(queryset, fields, level=level+1, store=store)
