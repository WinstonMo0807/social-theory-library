from uuid import UUID


def filter_slug_or_uuid(queryset, value: str, *, slug_field: str, id_field: str):
    """Filter an entity reference without coercing a human slug to UUID.

    Combining a slug lookup and UUID lookup in one ``Q`` object still asks the
    database backend to prepare the UUID value.  A normal slug such as
    ``sociology`` then raises a validation error before SQL is executed.
    """

    try:
        identifier = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return queryset.filter(**{slug_field: value})
    return queryset.filter(**{id_field: identifier})
