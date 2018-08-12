import json
from rest_framework.filters import SearchFilter
from rest_framework.test import APITestCase

from example.models import Author, Blog, Entry
from example.serializers import EntrySerializer
from rest_framework_json_api.backends import (
    JSONAPIFilterFilter,
    JSONAPIOrderingFilter,
    JSONAPIQueryValidationFilter
)
from rest_framework_json_api.pagination import JsonApiPageNumberPagination
from rest_framework_json_api.views import ModelViewSet

try:
    from unittest import mock
except ImportError:
    import mock

# for lack of better sample data, I just grabbed some from a schedule of classes.
BLOGS_DATA = [
    {"name": "ANTB", "tagline": "ANTHROPOLOGY (BARNARD)"},
    {"name": "CLSB", "tagline": "CLASSICS (BARNARD)"},
    {"name": "AMSB", "tagline": "AMERICAN STUDIES (BARNARD)"},
    {"name": "CHMB", "tagline": "CHEMISTRY (BARNARD)"},
    {"name": "ARHB", "tagline": "ART HISTORY (BARNARD)"},
    {"name": "ITLB", "tagline": "ITALIAN (BARNARD)"},
    {"name": "BIOB", "tagline": "BIOLOGICAL SCIENCES (BARNARD)"},
]

ENTRIES_DATA = [
    {
        "blog": "ANTB",
        "headline": "ANTH1009V",
        "body_text": "INTRO TO LANGUAGE & CULTURE",
    },
    {
        "blog": "CLSB",
        "headline": "CLCV2442V",
        "body_text": "EGYPT IN CLASSICAL WORLD-DISC",
    },
    {
        "blog": "AMSB",
        "headline": "AMST3704X",
        "body_text": "SENIOR RESEARCH ESSAY SEMINAR",
    },
    {
        "blog": "ANTB",
        "headline": "ANTH3976V",
        "body_text": "ANTHROPOLOGY OF SCIENCE",
    },
    {
        "blog": "CHMB",
        "headline": "CHEM3271X",
        "body_text": "INORGANIC CHEMISTRY",
    },
    {
        "blog": "ARHB",
        "headline": "AHIS3915X",
        "body_text": "ISLAM AND MEDIEVAL WEST",
    },
    {
        "blog": "ANTB",
        "headline": "ANTH3868X",
        "body_text": "ETHNOGRAPHIC FIELD RESEARCH IN NYC",
    },
    {
        "blog": "ITLB",
        "headline": "CLIA3660V",
        "body_text": "MAFIA MOVIES",
    },
    {
        "blog": "ARHB",
        "headline": "AHIS3999X",
        "body_text": "INDEPENDENT RESEARCH",
    },
    {
        "blog": "BIOB",
        "headline": "BIOL3594X",
        "body_text": "SENIOR THESIS SEMINAR",
    },
]

ENTRIES = "/entries"


# TODO: This code is not likely to be merged immediately so keep the files self-contained
# rather than editing example.views. Just use mock.patch to switch the ViewSet.


class MySearchParamMixin(object):
    search_param = 'filter[all]'


class MyJSONAPIFilterFilter(MySearchParamMixin, JSONAPIFilterFilter):
    pass


class MySearchFilter(MySearchParamMixin, SearchFilter):
    pass


class MyPagination(JsonApiPageNumberPagination):
    page_size = 100


class MyEntryViewSet(ModelViewSet):
    queryset = Entry.objects.all()
    serializer_class = EntrySerializer
    filter_backends = (JSONAPIQueryValidationFilter, MySearchFilter,
                       MyJSONAPIFilterFilter, JSONAPIOrderingFilter)
    pagination_class = MyPagination
    rels = ('exact', 'iexact', 'icontains', 'gt', 'lt', 'in', 'regex')
    filterset_fields = {
        'id': ('exact', 'in'),
        'headline': rels,
        'body_text': rels,
        'blog__name': rels,
        'blog__tagline': rels,
    }
    search_fields = ('headline', 'body_text', 'id', 'blog__tagline', 'blog__name')


@mock.patch('example.views.EntryViewSet', MyEntryViewSet)
class DJATestParameters(APITestCase):
    """
    tests of query parameters: page, filter, fields, sort, include, and combinations thereof
    TODO: also test combinations of filter backends (leaving out, etc.)
    """

    def setUp(self):
        # for now, just authenticate as a superuser. This allows all methods.
        self.author = Author.objects.create(name='Poindexter', email='i.am@lost.com')
        self.blog = Blog.objects.create(name='Some courses', tagline="It's a blog")
        self.other_blog = Blog.objects.create(name='Other blog', tagline="It's another blog")

        # add enough data to test pagination, etc
        self.blogs = {}
        for b in BLOGS_DATA:
            self.blogs[b["name"]] = Blog.objects.create(
                name=b["name"],
                tagline=b["tagline"]
            )
        self.entries = []
        for c in ENTRIES_DATA:
            self.entries.append(Entry.objects.create(
                blog=self.blogs[c['blog']],
                headline=c['headline'],
                body_text=c['body_text'],
            ))

    def test01_invalid_parameters(self):
        response = self.client.get(ENTRIES + '?snort')
        self.assertEqual(response.status_code, 400)
        j = json.loads(response.content)
        self.assertEqual(j['errors'][0]['detail'], 'invalid query parameter: snort')
        response = self.client.get(ENTRIES + '?sort=abc,-headline,def')
        self.assertEqual(response.status_code, 400)
        j = json.loads(response.content)
        self.assertEqual(j['errors'][0]['detail'], 'invalid sort parameters: abc,def')
        response = self.client.get(ENTRIES + '?sort=headline&sort=-body_text')
        self.assertEqual(response.status_code, 400)
        j = json.loads(response.content)
        self.assertEqual(j['errors'][0]['detail'], 'repeated query parameter not allowed: sort')

    def test02_search_not_found(self):
        """
        test keyword search (SearchFilter): filter[all]=keywords
        find all entries with "nonesuch" (should be none)
        """
        response = self.client.get(ENTRIES + '?filter[all]=nonesuch')
        j = json.loads(response.content)
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(len(j['data']), 0)

    def test03_search_keyword(self):
        """
        find all entries with "research" in the bodyText (3 based on current test data)
        """
        response = self.client.get(ENTRIES + '?filter[all]=research')
        self.assertEqual(response.status_code, 200, msg=response.content)
        j = json.loads(response.content)
        self.assertGreater(len(j['data']), 0)
        for c in j['data']:
            attr = c['attributes']
            self.assertTrue('research' in attr['bodyText'].lower())

    def test04_search_keywords(self):
        """
        find all entries with "research" and "seminar" (1 based on current test data)
        """
        response = self.client.get(ENTRIES + '?filter[all]=research seminar')
        self.assertEqual(response.status_code, 200, msg=response.content)
        j = json.loads(response.content)
        self.assertGreater(len(j['data']), 0)
        for c in j['data']:
            attr = c['attributes']
            self.assertTrue('research' in attr['bodyText'].lower() and
                            'seminar' in attr['bodyText'].lower())

    def find_blog_id(self, id):
        for b in self.blogs.values():
            if b.id == int(id):
                return b
        return None

    def test05_search_related_keyword(self):
        """
        find all entries with "science" (some are in blog.tagline)
        """
        response = self.client.get(ENTRIES + '?filter[all]=science')
        self.assertEqual(response.status_code, 200, msg=response.content)
        j = json.loads(response.content)
        self.assertGreater(len(j['data']), 0)
        for c in j['data']:
            attr = c['attributes']
            blog_id = c['relationships']['blog']['data']['id']
            b = self.find_blog_id(blog_id)
            self.assertTrue('science' in attr['bodyText'].lower() or 'science' in b.tagline.lower())

    def test06_filter_exact(self):
        """
        search for an exact match
        """
        response = self.client.get(ENTRIES + '?filter[headline]=CHEM3271X')
        self.assertEqual(response.status_code, 200, msg=response.content)
        j = json.loads(response.content)
        self.assertEqual(len(j['data']), 1)

    def test07_filter_exact_fail(self):
        """
        failed search for an exact match
        """
        response = self.client.get(ENTRIES + '?filter[headline]=XXXXX')
        self.assertEqual(response.status_code, 200, msg=response.content)
        j = json.loads(response.content)
        self.assertEqual(len(j['data']), 0)

    def test08_filter_related(self):
        """
        filter via a relationship chain
        """
        response = self.client.get(ENTRIES + '?filter[blog.name]=ANTB')
        self.assertEqual(response.status_code, 200, msg=response.content)
        j = json.loads(response.content)
        self.assertEqual(len(j['data']), len([k for k in ENTRIES_DATA if k['blog'] == 'ANTB']))

    def test09_filter_fields_union_list(self):
        """
        test field for a list of values (ORed): ?filter[field.in]=val1,val2,val3
        """
        response = self.client.get(ENTRIES +
                                   '?filter[headline.in]=CLCV2442V,XXX,BIOL3594X')
        j = json.loads(response.content)
        self.assertEqual(response.status_code, 200, msg=response.content)
        self.assertEqual(len(j['data']),
                         len([k for k in ENTRIES_DATA if k['headline'] == 'CLCV2442V']) +
                         len([k for k in ENTRIES_DATA if k['headline'] == 'XXX']) +
                         len([k for k in ENTRIES_DATA if k['headline'] == 'BIOL3594X']),
                         msg="filter field list (union)")

    def test10_filter_fields_intersection(self):
        """
        test fields (ANDed): ?filter[field1]=val1&filter[field2]=val2
        """
        #
        response = self.client.get(ENTRIES +
                                   '?filter[headline.regex]=^A&filter[bodyText.icontains]=in')
        self.assertEqual(response.status_code, 200, msg=response.content)
        j = json.loads(response.content)
        self.assertGreater(len(j['data']), 1)
        self.assertEqual(len(j['data']),
                         len([k for k in ENTRIES_DATA if k['headline'].startswith('A') and
                              'in' in k['body_text'].lower()]))

    def test11_filter_invalid(self):
        """
        test for filter with invalid filter name
        """
        response = self.client.get(ENTRIES + '?filter[nonesuch]=CHEM3271X')
        self.assertEqual(response.status_code, 400, msg=response.content)
        j = json.loads(response.content)
        self.assertEqual(j['errors'][0]['detail'], "invalid filter[nonesuch]")

    def test12_sort(self):
        """
        test sort
        """
        response = self.client.get(ENTRIES + '?sort=headline')
        self.assertEqual(response.status_code, 200, msg=response.content)
        j = json.loads(response.content)
        headlines = [c['attributes']['headline'] for c in j['data']]
        sorted_headlines = [c['attributes']['headline'] for c in j['data']]
        sorted_headlines.sort()
        self.assertEqual(headlines, sorted_headlines)

    def test13_sort_reverse(self):
        """
        confirm switching the sort order actually works
        """
        response = self.client.get(ENTRIES + '?sort=-headline')
        self.assertEqual(response.status_code, 200, msg=response.content)
        j = json.loads(response.content)
        headlines = [c['attributes']['headline'] for c in j['data']]
        sorted_headlines = [c['attributes']['headline'] for c in j['data']]
        sorted_headlines.sort()
        self.assertNotEqual(headlines, sorted_headlines)

    def test14_sort_invalid(self):
        """
        test sort of invalid field
        """
        response = self.client.get(ENTRIES + '?sort=nonesuch,headline,-not_a_field')
        self.assertEqual(response.status_code, 400, msg=response.content)
        j = json.loads(response.content)
        self.assertEqual(j['errors'][0]['detail'], "invalid sort parameters: nonesuch,-not_a_field")
