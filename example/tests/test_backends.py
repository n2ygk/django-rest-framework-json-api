import json

import pytest
from django_filters import VERSION as dfver
from rest_framework.test import APITestCase

from example.models import Author, Blog, Entry

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

ENTRIES = "/backend-entries"


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
        self.assertEqual(response.status_code, 400, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(j['errors'][0]['detail'], 'invalid query parameter: snort')
        response = self.client.get(ENTRIES + '?sort=abc,-headline,def')
        self.assertEqual(response.status_code, 400, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(j['errors'][0]['detail'], 'invalid sort parameters: abc,def')
        response = self.client.get(ENTRIES + '?sort=headline&sort=-body_text')
        self.assertEqual(response.status_code, 400, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(j['errors'][0]['detail'], 'repeated query parameter not allowed: sort')

    def test02_search_not_found(self):
        """
        test keyword search (SearchFilter): filter[search]=keywords
        find all entries with "nonesuch" (should be none)
        """
        response = self.client.get(ENTRIES + '?filter[search]=nonesuch')
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        self.assertEqual(len(j['data']), 0)

    def test03_search_keyword(self):
        """
        find all entries with "research" in the bodyText (3 based on current test data)
        """
        response = self.client.get(ENTRIES + '?filter[search]=research')
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertGreater(len(j['data']), 0)
        for c in j['data']:
            attr = c['attributes']
            self.assertTrue('research' in attr['bodyText'].lower())

    def test04_search_keywords(self):
        """
        find all entries with "research" and "seminar" (1 based on current test data)
        """
        response = self.client.get(ENTRIES + '?filter[search]=research seminar')
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
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
        response = self.client.get(ENTRIES + '?filter[search]=science')
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertGreater(len(j['data']), 0)
        for c in j['data']:
            attr = c['attributes']
            blog_id = c['relationships']['blog']['data']['id']
            b = self.find_blog_id(blog_id)
            self.assertTrue('science' in attr['bodyText'].lower() or 'science' in b.tagline.lower())

    # TODO: unable to get django-filter < 2.0 (required for py27) to work. Do we care?
    @pytest.mark.xfail((dfver) <= (2, 0), reason="django-filter < 2.0 fails for unknown reason")
    def test06_filter_exact(self):
        """
        search for an exact match
        """
        response = self.client.get(ENTRIES + '?filter[headline]=CHEM3271X')
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(len(j['data']), 1)

    @pytest.mark.xfail((dfver) <= (2, 0), reason="django-filter < 2.0 fails for unknown reason")
    def test07_filter_exact_fail(self):
        """
        failed search for an exact match
        """
        response = self.client.get(ENTRIES + '?filter[headline]=XXXXX')
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(len(j['data']), 0)

    @pytest.mark.xfail((dfver) <= (2, 0), reason="django-filter < 2.0 fails for unknown reason")
    def test08_filter_related(self):
        """
        filter via a relationship chain
        """
        response = self.client.get(ENTRIES + '?filter[blog.name]=ANTB')
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(len(j['data']), len([k for k in ENTRIES_DATA if k['blog'] == 'ANTB']))

    @pytest.mark.xfail((dfver) <= (2, 0), reason="django-filter < 2.0 fails for unknown reason")
    def test09_filter_fields_union_list(self):
        """
        test field for a list of values (ORed): ?filter[field.in]=val1,val2,val3
        """
        response = self.client.get(ENTRIES +
                                   '?filter[headline.in]=CLCV2442V,XXX,BIOL3594X')
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        self.assertEqual(len(j['data']),
                         len([k for k in ENTRIES_DATA if k['headline'] == 'CLCV2442V']) +
                         len([k for k in ENTRIES_DATA if k['headline'] == 'XXX']) +
                         len([k for k in ENTRIES_DATA if k['headline'] == 'BIOL3594X']),
                         msg="filter field list (union)")

    @pytest.mark.xfail((dfver) <= (2, 0), reason="django-filter < 2.0 fails for unknown reason")
    def test10_filter_fields_intersection(self):
        """
        test fields (ANDed): ?filter[field1]=val1&filter[field2]=val2
        """
        #
        response = self.client.get(ENTRIES +
                                   '?filter[headline.regex]=^A&filter[bodyText.icontains]=in')
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertGreater(len(j['data']), 1)
        self.assertEqual(len(j['data']),
                         len([k for k in ENTRIES_DATA if k['headline'].startswith('A') and
                              'in' in k['body_text'].lower()]))

    @pytest.mark.xfail((dfver) <= (2, 0), reason="django-filter < 2.0 fails for unknown reason")
    def test11_filter_invalid(self):
        """
        test for filter with invalid filter name
        """
        response = self.client.get(ENTRIES + '?filter[nonesuch]=CHEM3271X')
        self.assertEqual(response.status_code, 400, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(j['errors'][0]['detail'], "invalid filter[nonesuch]")

    def test12_sort(self):
        """
        test sort
        """
        response = self.client.get(ENTRIES + '?sort=headline')
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        headlines = [c['attributes']['headline'] for c in j['data']]
        sorted_headlines = [c['attributes']['headline'] for c in j['data']]
        sorted_headlines.sort()
        self.assertEqual(headlines, sorted_headlines)

    def test13_sort_reverse(self):
        """
        confirm switching the sort order actually works
        """
        response = self.client.get(ENTRIES + '?sort=-headline')
        self.assertEqual(response.status_code, 200, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        headlines = [c['attributes']['headline'] for c in j['data']]
        sorted_headlines = [c['attributes']['headline'] for c in j['data']]
        sorted_headlines.sort()
        self.assertNotEqual(headlines, sorted_headlines)

    def test14_sort_invalid(self):
        """
        test sort of invalid field
        """
        response = self.client.get(ENTRIES + '?sort=nonesuch,headline,-not_a_field')
        self.assertEqual(response.status_code, 400, msg=response.content.decode("utf-8"))
        j = json.loads(response.content.decode("utf-8"))
        self.assertEqual(j['errors'][0]['detail'], "invalid sort parameters: nonesuch,-not_a_field")
