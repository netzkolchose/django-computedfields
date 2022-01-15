from typing import Callable, List, Optional, OrderedDict, Sequence, Tuple, TypeVar, Any, Dict, Type, Union, overload
from django.db.models import Field, Model, QuerySet

_ST = TypeVar("_ST", contravariant=True)
_GT = TypeVar("_GT", covariant=True)
F = TypeVar('F', bound=Callable[..., Any])


class Resolver:
    def computed(
        self,
        field: Field[_ST, _GT],
        depends: Optional[List[Tuple[str, List[str]]]]
    ) -> Callable[[Callable[..., _ST]], _GT]:
        ...

    def get_contributing_fks(self) -> Dict[Type[Model], Optional[List[str]]]: ...
    def has_computedfields(self, model: Type[Model]) -> bool: ...
    def get_computedfields(self, model: Type[Model]) -> List[str]: ...
    def is_computedfield(self, model: Type[Model], fieldname: str) -> bool: ...

    def update_computedfields(
        self,
        instance: Model,
        update_fields: Optional[Sequence[str]] = None
    ) -> Optional[Sequence[str]]: ...
    def compute(self, instance: Model, fieldname: str) -> Any: ...

    def update_dependent(
        self,
        instance: Union[QuerySet, Model],
        model: Optional[Type[Model]] = None,
        update_fields: Optional[Sequence[str]] = None,
        old: Optional[OrderedDict[Type[Model], Any]] = None,
        update_local: Optional[bool] = None
    ) -> None:
        ...

    def preupdate_dependent(
        self,
        instance: Union[QuerySet, Model],
        model: Optional[Type[Model]] = None,
        update_fields: Optional[Sequence[str]] = None
    ) -> OrderedDict[Type[Model], Any]:
        ...
    
    def update_dependent_multi(
        self,
        instances: Sequence[Union[QuerySet, Model]],
        old: Optional[OrderedDict[Type[Model], Any]] = None,
        update_local: Optional[bool] = None
    ) -> None:
        ...

    def preupdate_dependent_multi(
        self,
        instances: Sequence[Union[QuerySet, Model]],
    ) -> OrderedDict[Type[Model], Any]:
        ...

    @overload
    def precomputed(self, f: F) -> F: ...
    @overload
    def precomputed(self, skip_after: bool) -> Callable[[F], F]: ...

    computed_models: Dict[Type[Model], Dict[str, Field]]

    # internals
    def _querysets_for_update(self, model, instance, update_fields=None, pk_list=False): ...
    def bulk_updater(self, queryset, update_fields, return_pks=False, local_only=False): ...
    _fk_map: Dict[Type[Model], Optional[List[str]]]
    _m2m: Dict[Type[Model], Optional[Dict[str, str]]]


active_resolver: Resolver

class _ComputedFieldsModelBase:
    ...

