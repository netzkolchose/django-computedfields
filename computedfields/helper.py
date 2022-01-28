from itertools import tee, zip_longest
from django.db.models import Model, QuerySet
from typing import Any, Iterable, Iterator, List, Sequence, Type, TypeVar, Tuple
from django.db.backends.base.base import BaseDatabaseWrapper

T = TypeVar('T', covariant=True)


def pairwise(iterable: Sequence[T]) -> Iterator[Tuple[T, T]]:
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def modelname(model: Type[Model]) -> str:
    return f'{model._meta.app_label}.{model._meta.model_name}'


def is_sublist(needle: Sequence[Any], haystack: Sequence[Any]) -> bool:
    if not needle:
        return True
    if not haystack:
        return False
    max_k = len(needle) - 1
    k = 0
    for elem in haystack:
        if elem != needle[k]:
            k = 0
            continue
        if k == max_k:
            return True
        k += 1
    return False


def parent_to_inherited_path(parent: Type[Model], inherited: Type[Model]) -> List[str]:
    """
    Pull relation path segments from `parent` to `inherited` model
    in multi table inheritance.
    """
    bases = inherited._meta.get_base_chain(parent)
    relations: List[str] = []
    model = inherited
    for base in bases:
        relations.append(model._meta.parents[base].remote_field.name)
        model = base
    return relations[::-1]


def skip_equal_segments(ps: Sequence[str], rs: Sequence[str]) -> List[str]:
    """
    Skips all equal segments from the beginning of `ps` and `rs`
    returning left over segments from `ps`.
    """
    add: bool = False
    ret: List[str] = []
    for left, right in zip_longest(ps, rs):
        if left is None:
            break
        if left != right:
            add = True
        if add:
            ret.append(left)
    return ret


def subquery_pk(qs: QuerySet, connection: BaseDatabaseWrapper) -> Iterable[Any]:
    if connection.vendor == 'mysql':
        return set(qs.values_list('pk', flat=True))
    return qs.values('pk')
