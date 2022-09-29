from time import time
from datetime import timedelta
from argparse import FileType
from django.apps import apps
from json import loads

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from computedfields.models import active_resolver
from computedfields.helper import modelname, slice_iterator
from computedfields.settings import settings
from ._helpers import retrieve_computed_models, HAS_TQDM, tqdm

from typing import Type, cast
from django.db.models import Model


# TODO:
# - use eprint like in checkdata
# - silent switch?
# - better progress update story in bulk/fast (signals?)
# - better distinct handling


class Command(BaseCommand):
    help = 'Update computed fields.'

    def add_arguments(self, parser):
        parser.add_argument(
            'args',
            metavar='app_label[.ModelName]',
            nargs='*',
            help='Update computed fields in specified app_label or app_label.ModelName.',
        )
        parser.add_argument(
            '--from-json',
            type=FileType('r'),
            default=None,
            help='Update from JSONL desync listing (exported by checkdata with --json).'
        )
        parser.add_argument(
            '-p', '--progress',
            action='store_true',
            help='Show update progress.',
        )
        parser.add_argument(
            '-m', '--mode',
            default='default',
            type=str,
            choices=('loop', 'bulk', 'fast'),
            help='Set explicit update mode, default: bulk/fast from settings.py.'
        )
        parser.add_argument(
            '-q', '--querysize',
            default=settings.COMPUTEDFIELDS_QUERYSIZE,
            type=int,
            help='Set queryset size, default: 10000 or value from settings.py.'
        )

    def handle(self, *app_labels, **options):
        start_time = time()
        fileinput = options['from_json']
        progress = options['progress']
        mode = options['mode']
        size = options['querysize']
        if fileinput and app_labels:
            raise CommandError('Provide either applabel.ModelName listing, or --from-file.')
        if progress and not HAS_TQDM:
            raise CommandError('Package "tqdm" needed for the progressbar.')
        if fileinput:
            self.action_fileinput(fileinput, size, progress)
        else:
            models = retrieve_computed_models(app_labels)
            getattr(self, 'action_' + mode, self.action_default)(models, size, progress)
        end_time = time()
        duration = int(end_time - start_time)
        print(f'\nTotal update time: {timedelta(seconds=duration)}')

    @transaction.atomic
    def action_fileinput(self, file, size, progress):
        print(self.style.WARNING('Updating from desync data:'), file.name)
        for line in file:
            data = loads(line)
            model_name, desync = data.get('model'), data.get('desync')
            model: Type[Model] = cast(Type[Model], apps.get_model(model_name))
            amount = len(desync)
            fields = set(active_resolver.computed_models[model].keys())
            print(f'- {self.style.MIGRATE_LABEL(modelname(model))}')
            print(f'  Fields: {", ".join(fields)}')
            print(f'  Desync Records: {amount}')
            print(f'  Querysize: {active_resolver.get_querysize(model, fields, size)}')
            if not amount:
                continue
            if progress:
                qsize = size
                if qsize > amount/100:
                    qsize = amount // 100 or 1
                with tqdm(total=amount, desc='  Update', unit=' rec') as bar:
                    pos = 0
                    while pos < amount:
                        active_resolver.update_dependent(model._base_manager.filter(pk__in=desync[pos:pos+qsize]))
                        progressed = min(pos+qsize, amount) - pos
                        bar.update(progressed)
                        pos += qsize
            else:
                active_resolver.update_dependent(model._base_manager.filter(pk__in=desync))

    @transaction.atomic
    def action_default(self, models, size, show_progress, mode=''):
        """
        Runs either in fast or bulk mode, whatever was set in settings.
        """
        if not mode:
            mode = 'fast' if settings.COMPUTEDFIELDS_FASTUPDATE else 'bulk'
            print(f'Update mode: settings.py --> {mode}')

        print(f'Default querysize: {size}')
        print('Models:')
        for model in models:
            qs = model._base_manager.all()
            amount = qs.count()
            fields = set(active_resolver.computed_models[model].keys())
            print(f'- {self.style.MIGRATE_LABEL(modelname(model))}')
            print(f'  Fields: {", ".join(fields)}')
            print(f'  Records: {amount}')
            print(f'  Querysize: {active_resolver.get_querysize(model, fields, size)}')

            # TODO: dummy test code to get some idea about long taking tasks in the update tree
            # this is linked to bad perf from slicing and distinct() calls in bulk_updater (#101)
            ##qs = qs.filter(pk__in=range(1, 1001))
            #counted = count_dependent(qs)
            #explained = explain_dependent(qs, query_pks=False)
            #print('records to check:', counted)
            #for ex in explained:
            #    print(ex)
            #timer(lambda: explain_dependent(qs), 1)
            #timer(lambda: count_dependent(qs), 1)
            #return

            if not amount:
                continue
            if show_progress:
                # to show progress we use slices for now, which penalizes big batches alot
                # TODO: use update signals once we have those
                # adjust stepping for small amounts, so we still get a meaningful progressbar
                qsize = size
                if qsize > amount/100:
                    qsize = amount // 100 or 1
                with tqdm(total=amount, desc='  Progress', unit=' rec') as bar:
                    pos = 0
                    while pos < amount:
                        active_resolver.update_dependent(qs.order_by('pk')[pos:pos+qsize], querysize=qsize)
                        progress = min(pos+qsize, amount) - pos
                        bar.update(progress)
                        pos += qsize
            else:
                active_resolver.update_dependent(qs, querysize=size)

    def action_bulk(self, models, size, show_progress):
        active_resolver.use_fastupdate = False
        print('Update mode: bulk')
        self.action_default(models, size, show_progress, 'bulk')

    def action_fast(self, models, size, show_progress):
        active_resolver.use_fastupdate = True
        active_resolver._batchsize = settings.COMPUTEDFIELDS_BATCHSIZE_FAST
        print('Update mode: fast')
        self.action_default(models, size, show_progress, 'fast')

    @transaction.atomic
    def action_loop(self, models, size, show_progress):
        print('Update mode: loop')
        print(f'Global querysize: {size}')
        print('Models:')
        if size != settings.COMPUTEDFIELDS_QUERYSIZE:
            # patch django settings in case querysize was explicitly given
            # needed here, as we have no other API to announce the changed value
            from django.conf import settings as ds
            ds.COMPUTEDFIELDS_QUERYSIZE = size
        for model in models:
            qs = model._base_manager.all()
            amount = qs.count()
            fields = list(active_resolver.computed_models[model].keys())
            qsize = active_resolver.get_querysize(model, fields, size)
            print(f'- {self.style.MIGRATE_LABEL(modelname(model))}')
            print(f'  Fields: {", ".join(fields)}')
            print(f'  Records: {amount}')
            print(f'  Querysize: {qsize}')
            if not amount:
                continue
            # also apply select/prefetch rules
            select = active_resolver.get_select_related(model, fields)
            prefetch = active_resolver.get_prefetch_related(model, fields)
            if select:
                qs = qs.select_related(*select)
            if prefetch:
                qs = qs.prefetch_related(*prefetch)
            if show_progress:
                with tqdm(total=amount, desc='  Progress', unit=' rec') as bar:
                    for obj in slice_iterator(qs, qsize):
                        obj.save()
                        bar.update(1)
            else:
                for obj in slice_iterator(qs, qsize):
                    obj.save()


# get some explaining on update_dependent
#def count_dependent(queryset, fields=None):
#    #counted = queryset.count()
#    counted = len(set(queryset.values_list('pk', flat=True).iterator()))
#    if counted:
#        updates = active_resolver._querysets_for_update(queryset.model, queryset, fields).values()
#        for qs, f in updates:
#            counted += count_dependent(qs, f)
#    return counted
#
#def explain_dependent(queryset, fields=None, level=0, query_pks=False):
#    s = time()
#    #counted = queryset.count()
#    counted = len(set(queryset.values_list('pk', flat=True).iterator()))
#    d = time() - s
#    res = [(level, queryset.model, fields, counted, d, queryset.distinct().values_list('pk', flat=True) if query_pks else [])]
#    if counted:
#        updates = active_resolver._querysets_for_update(queryset.model, queryset, fields).values()
#        for qs, f in updates:
#            res += explain_dependent(qs, f, level+1, query_pks)
#    return res
#
#
#def timer(f, n):
#    start = time()
#    for _ in range(n):
#        f()
#    print(time()-start)
