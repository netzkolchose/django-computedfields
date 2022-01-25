"""
``fast_update`` drop-in to avoid bad performance with ``bulk_update``.

The update is based on 'UPDATE FROM VALUES' variants, which performs much better
for bigger changesets.

Currently supported DBMS:
- sqlite 3.33+ (3.37 and 3.38 tested)
- postgresql (14 tested, should work with all versions 9.1+)
- mariabd 10.3+
- mysql 8

Note:
Support testing of db backends is still wonky, thus you should check yourself,
if your updates get properly applied.

Usage:
>>> from fast_update import fast_update
>>> fast_update(MyModel.objects.all(), [list of changed model objects], [fieldnames to update])
"""

from django.db.models.functions import Cast
from django.db.models.expressions import Col
from django.db import transaction
from django.db.utils import ProgrammingError
import logging

logger = logging.getLogger(__name__)

# typing imports
from django.db.models import Field, QuerySet, Model
from django.db.models.sql.compiler import SQLCompiler
from typing import Any, Dict, Iterable, List, Optional, Sequence, Type


def _cast_col_postgres(tname: str, field: Field, compiler: SQLCompiler, connection: Any) -> str:
    return Cast(Col(tname, field), output_field=field).as_postgresql(compiler, connection)[0]


def as_dummy(
    tname: str,
    pkname: str,
    fields: Sequence[Field],
    count: int,
    compiler: SQLCompiler,
    connection: Any
) -> str:
    return ''


def as_postgresql(
    tname: str,
    pkname: str,
    fields: Sequence[Field],
    count: int,
    compiler: SQLCompiler,
    connection: Any
) -> str:
    dname = 'd' if tname != 'd' else 'c'
    cols = ','.join(f'"{f.column}"={_cast_col_postgres(dname, f, compiler, connection)}' for f in fields)
    value = f'({",".join(["%s"] * (len(fields) + 1))})'
    values = ','.join([value] * count)
    dcols = f'"{pkname}",' + ','.join(f'"{f.column}"' for f in fields)
    where = f'"{tname}"."{pkname}"="{dname}"."{pkname}"'
    return f'UPDATE "{tname}" SET {cols} FROM (VALUES {values}) AS "{dname}" ({dcols}) WHERE {where}'


def as_sqlite(
    tname: str,
    pkname: str,
    fields: Sequence[Field],
    count: int,
    compiler: SQLCompiler,
    connection: Any
) -> str:
    dname = 'd' if tname != 'd' else 'c'
    cols = ','.join(f'"{f.column}"="{dname}"."column{i + 2}"' for i, f in enumerate(fields))
    value = f'({",".join(["%s"] * (len(fields) + 1))})'
    values = ','.join([value] * count)
    where = f'"{tname}"."{pkname}"="{dname}"."column1"'
    return f'UPDATE "{tname}" SET {cols} FROM (VALUES {values}) AS "{dname}" WHERE {where}'


def as_mysql(
    tname: str,
    pkname: str,
    fields: Sequence[Field],
    count: int,
    compiler: SQLCompiler,
    connection: Any
) -> str:
    dname = 'd' if tname != 'd' else 'c'
    cols = ','.join(f'`{f.column}`={dname}.{i+1}' for i, f in enumerate(fields))
    value = f'({",".join(["%s"] * (len(fields) + 1))})'
    values = ",".join([value] * (count + 1))
    on = f'`{tname}`.`{pkname}` = {dname}.0'
    return f'UPDATE `{tname}` INNER JOIN (VALUES {values}) AS {dname} ON {on} SET {cols}'


def as_mysql8(
    tname: str,
    pkname: str,
    fields: Sequence[Field],
    count: int,
    compiler: SQLCompiler,
    connection: Any
) -> str:
    dname = 'd' if tname != 'd' else 'c'
    cols = ','.join(f'`{f.column}`={dname}.column_{i+1}' for i, f in enumerate(fields))
    value = f'ROW({",".join(["%s"] * (len(fields) + 1))})'
    values = ",".join([value] * count)
    on = f'`{tname}`.`{pkname}` = {dname}.column_0'
    return f'UPDATE `{tname}` INNER JOIN (VALUES {values}) AS {dname} ON {on} SET {cols}'


QUERY = {
    'sqlite': as_sqlite,
    'postgresql': as_postgresql,
    'mysql': as_mysql,
    'mysql8': as_mysql8
}

# decide at runtine on connection level, which mysql impl to use
CONNECTION_HASHES: Dict[int, str] = {}

def _adjust_mysql(connection: Any) -> str:
    if connection.connection:
        vendor = CONNECTION_HASHES.get(hash(connection.connection), None)
        if vendor is not None:
            return vendor
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SELECT foo.0 FROM (VALUES (0, 1), (1, 'zzz'),(2, 'yyy')) as foo")
            CONNECTION_HASHES[hash(connection.connection)] = 'mysql'
            return 'mysql'
    except ProgrammingError:
        pass
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SELECT column_1 FROM (VALUES ROW(1, 'zzz'), ROW(2, 'yyy')) as foo")
            CONNECTION_HASHES[hash(connection.connection)] = 'mysql8'
            return 'mysql8'
    except ProgrammingError:
        pass
    CONNECTION_HASHES[hash(connection.connection)] = ''
    logger.warning('mysql backend without UPDATE FROM VALUES support, falling back to bulk_update')
    return ''


def fast_update(qs: QuerySet, objs: Iterable[Any], fieldnames: Sequence[str], batch_size: int = 1000) -> None:
    model: Type[Model] = qs.model

    # filter all non model local fields --> still handled by bulk_update
    non_local_fieldnames = []
    local_fieldnames = []
    for f in fieldnames:
        if model._meta.get_field(f) not in model._meta.local_fields:
            non_local_fieldnames.append(f)
        else:
            local_fieldnames.append(f)
        
    # avoid more expensive doubled updates
    if non_local_fieldnames and len(local_fieldnames) < 2:
        return model.objects.bulk_update(objs, fieldnames, batch_size)
    
    if local_fieldnames:
        from django.db import connections

        tablename = model._meta.db_table
        pk_field = model._meta.pk
        if not pk_field:
            return model.objects.bulk_update(objs, fieldnames, batch_size)
        fields = [model._meta.get_field(f) for f in local_fieldnames]
        compiler = qs.query.get_compiler(qs.db)
        connection = connections[qs.db]

        # construct update data
        data = []
        counter = 0
        batches = []
        for o in objs:
            counter += 1
            # pk as first value to "join" on
            sub = [pk_field.get_db_prep_save(getattr(o, pk_field.attname), connection)]
            for field in fields:
                sub.append(field.get_db_prep_save(getattr(o, field.attname), connection))
            data += sub
            if counter >= batch_size:
                batches.append((counter, data))
                data = []
                counter = 0
        if data:
            batches.append((counter, data))

        sql = ''
        last_counter = -1
        vendor = connection.vendor
        if vendor == 'mysql':
            vendor = _adjust_mysql(connection)
        for counter, data in batches:
            # construct update string
            if counter != last_counter:
                sql = QUERY.get(vendor, as_dummy)(
                    tablename, pk_field.column, fields, counter, compiler, connection)
                if not sql:
                    # exist with bulk_update for non supported db backends
                    return model.objects.bulk_update(objs, fieldnames, batch_size)
            
            if vendor == 'mysql':
                # mysql needs data patch with (0,1,2,...) as first VALUES entry
                data = list(range(len(fields) + 1)) + data

            with connection.cursor() as cur:
                cur.execute(sql, data)
    
    if non_local_fieldnames:
        model.objects.bulk_update(objs, non_local_fieldnames, batch_size)


def check_support(using: str = 'default') -> bool:
    from django.db import connections
    connection = connections[using]
    if connection.vendor == 'postgresql':
        return True
    elif connection.vendor == 'sqlite':
        # FIXME: also test 3.33 - 3.36 versions
        import importlib
        _mod = importlib.import_module(connection.connection.__class__.__module__)
        major, minor, _ = _mod.sqlite_version_info
        if major >= 3 and minor > 32:
            return True
    elif connection.vendor == 'mysql':
        if _adjust_mysql(connection):
            return True
    return False
