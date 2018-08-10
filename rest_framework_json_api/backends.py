from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend, OrderingFilter
from rest_framework.settings import api_settings

from django_filters.rest_framework import DjangoFilterBackend

from .settings import json_api_settings
from .utils import format_value


class JSONAPIQueryValidationFilter(BaseFilterBackend):
    """
    A backend filter that performs strict validation of query parameters for jsonapi spec
    conformance and raises a 400 error if non-conforming usage is found.

    TODO: For jsonapi error object conformance, must set jsonapi errors "parameter" for the
          ValidationError. This requires extending DRF/DJA Exceptions.
    """
    query_keywords = ('sort', 'filter', 'fields', 'page', 'include')

    def validate_query_params(self, request):
        """
        Validate that query params are in the list of valid `jsonapi_query_keywords`
        Raises ValidationError if not.
        """
        for qp in request.query_params.keys():
            bracket = qp.find('[')
            if bracket >= 0:
                if qp[-1] != ']':
                    raise ValidationError(
                        'invalid query parameter: {}'.format(qp))
                keyword = qp[:bracket]
            else:
                keyword = qp
            if keyword not in self.query_keywords:
                raise ValidationError(
                    'invalid query parameter: {}'.format(keyword))
            # catch errors like `?page[size]=3&page[size]=4` or `?sort=a,b,c&sort=d,e,f`:
            if len(request.query_params.getlist(qp)) > 1:
                raise ValidationError(
                    'repeated query parameter not allowed: {}'.format(qp))

    def filter_queryset(self, request, queryset, view):
        self.validate_query_params(request)
        return queryset


class JSONAPIOrderingFilter(OrderingFilter):
    """
    The standard rest_framework.filters.OrderingFilter works mostly fine as is,
    but with .ordering_param = 'sort' and some strict conformance checking.

    This implements http://jsonapi.org/format/#fetching-sorting and raises 400
    if any sort field is invalid. If you prefer *not* to report 400 errors for invalid
    sort fields, just use OrderingFilter with `ordering_param='sort'`

    TODO: Add sorting based upon relationship attributes (sort=relname.fieldname)
    """
    ordering_param = 'sort'

    def remove_invalid_fields(self, queryset, fields, view, request):
        """
        overrides remove_invalid_fields to raise a 400 exception instead of silently removing them.
        set `ignore_bad_sort_fields = True` to not do this validation.
        """
        valid_fields = [item[0] for item
                        in self.get_valid_fields(queryset, view, {'request': request})]
        bad_terms = [term for term
                     in fields if format_value(term.lstrip('-'), "underscore") not in valid_fields]
        if bad_terms:
            raise ValidationError(
                'invalid sort parameter{}: {}'.format(('s' if len(bad_terms) > 1 else ''),
                                                      ','.join(bad_terms)))

        return super(JSONAPIOrderingFilter, self).remove_invalid_fields(queryset,
                                                                        fields, view, request)



class JSONAPIFilterFilter(DjangoFilterBackend):
    """
    Overrides django_filters.rest_framework.DjangoFilterBackend to use `filter[field]` query
    parameter.

    This is not part of the jsonapi standard per-se, other than the requirement to use the `filter`
    keyword: This is an optional implementation of style of filtering in which each filter is an ORM
    expression as implemented by DjangoFilterBackend and seems to be in alignment with an
    interpretation of http://jsonapi.org/recommendations/#filtering, including relationship
    chaining.

    Filters can be:
    - A resource field equality test:
        `?filter[foo]=123`
    - Apply other relational operators:
        `?filter[foo.in]=bar,baz or ?filter[count.ge]=7...`
    - Membership in a list of values (OR):
        `?filter[foo]=abc,123,zzz (foo in ['abc','123','zzz'])`
    - Filters can be combined for intersection (AND):
        `?filter[foo]=123&filter[bar]=abc,123,zzz&filter[...]`
    - A related resource field for above tests:
        `?filter[foo.rel.baz]=123 (where `rel` is the relationship name)`

    It is meaningless to intersect the same filter: ?filter[foo]=123&filter[foo]=abc will
    always yield nothing so detect this repeated appearance of the same filter in
    JSONAPIQueryValidationFilter, above, and complain there.
    """
    search_param = api_settings.SEARCH_PARAM

    def __init__(self):
        self.filter_keys = []  # TODO: why do I need this?

    def get_filterset(self, request, queryset, view):
        """
        Validate that the `filter[field]` is defined in the filters and raise ValidationError if
        it's missing.

        While `filter` syntax and semantics is undefined by the jsonapi 1.0 spec, this behavior is
        consistent with the style used for missing query parameters:
        http://jsonapi.org/format/#query-parameters. In general, unlike django/DRF, jsonapi
        raises 400 rather than ignoring "bad" query parameters.
        """
        fs = super(JSONAPIFilterFilter, self).get_filterset(request, queryset, view)
        for k in self.filter_keys:
            if k not in fs.filters:
                raise ValidationError("invalid filter[{}]".format(k))
        return fs

    def get_filterset_kwargs(self, request, queryset, view):
        """
        Turns filter[<field>]=<value> into <field>=<value> which is what DjangoFilterBackend expects
        """
        self.filter_keys = []
        # rewrite `filter[field]` query parameters to make DjangoFilterBackend work.
        data = request.query_params.copy()
        for qp, val in data.items():
            if qp[:7] == 'filter[' and qp[-1] == ']' and qp != self.search_param:
                # convert jsonapi relationship path to Django ORM's __ notation:
                key = qp[7:-1].replace('.', '__')
                # undo JSON_API_FORMAT_FIELD_NAMES conversion:
                key = format_value(key, 'underscore')
                data[key] = val
                self.filter_keys.append(key)
                del data[qp]
        return {
            'data': data,
            'queryset': queryset,
            'request': request,
        }
