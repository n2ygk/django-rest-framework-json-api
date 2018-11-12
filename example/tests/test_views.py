import json

from django.test import RequestFactory
from django.utils import timezone
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.reverse import reverse
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from rest_framework_json_api.utils import format_resource_type

from . import TestBase
from .. import views
from example.factories import AuthorFactory, CommentFactory, EntryFactory
from example.models import Author, Blog, Comment, Entry, Course, Term
from example.serializers import AuthorBioSerializer, AuthorTypeSerializer, EntrySerializer
from example.views import AuthorViewSet

try:
    from unittest import mock
except ImportError:
    import mock


class TestRelationshipView(APITestCase):
    def setUp(self):
        self.author = Author.objects.create(name='Super powerful superhero', email='i.am@lost.com')
        self.blog = Blog.objects.create(name='Some Blog', tagline="It's a blog")
        self.other_blog = Blog.objects.create(name='Other blog', tagline="It's another blog")
        self.first_entry = Entry.objects.create(
            blog=self.blog,
            headline='headline one',
            body_text='body_text two',
            pub_date=timezone.now(),
            mod_date=timezone.now(),
            n_comments=0,
            n_pingbacks=0,
            rating=3
        )
        self.second_entry = Entry.objects.create(
            blog=self.blog,
            headline='headline two',
            body_text='body_text one',
            pub_date=timezone.now(),
            mod_date=timezone.now(),
            n_comments=0,
            n_pingbacks=0,
            rating=1
        )
        self.first_comment = Comment.objects.create(
            entry=self.first_entry, body="This entry is cool", author=None
        )
        self.second_comment = Comment.objects.create(
            entry=self.second_entry,
            body="This entry is not cool",
            author=self.author
        )

    def test_get_entry_relationship_blog(self):
        url = reverse(
            'entry-relationships', kwargs={'pk': self.first_entry.id, 'related_field': 'blog'}
        )
        response = self.client.get(url)
        expected_data = {'type': format_resource_type('Blog'), 'id': str(self.first_entry.blog.id)}

        assert response.data == expected_data

    def test_get_entry_relationship_invalid_field(self):
        response = self.client.get(
            '/entries/{}/relationships/invalid_field'.format(self.first_entry.id)
        )

        assert response.status_code == 404

    def test_get_blog_relationship_entry_set(self):
        response = self.client.get('/blogs/{}/relationships/entry_set'.format(self.blog.id))
        expected_data = [{'type': format_resource_type('Entry'), 'id': str(self.first_entry.id)},
                         {'type': format_resource_type('Entry'), 'id': str(self.second_entry.id)}]

        assert response.data == expected_data

    def test_put_entry_relationship_blog_returns_405(self):
        url = '/entries/{}/relationships/blog'.format(self.first_entry.id)
        response = self.client.put(url, data={})
        assert response.status_code == 405

    def test_patch_invalid_entry_relationship_blog_returns_400(self):
        url = '/entries/{}/relationships/blog'.format(self.first_entry.id)
        response = self.client.patch(url, data={'data': {'invalid': ''}})
        assert response.status_code == 400

    def test_relationship_view_errors_format(self):
        url = '/entries/{}/relationships/blog'.format(self.first_entry.id)
        response = self.client.patch(url, data={'data': {'invalid': ''}})
        assert response.status_code == 400

        result = json.loads(response.content.decode('utf-8'))

        assert 'data' not in result
        assert 'errors' in result

    def test_get_empty_to_one_relationship(self):
        url = '/comments/{}/relationships/author'.format(self.first_entry.id)
        response = self.client.get(url)
        expected_data = None

        assert response.data == expected_data

    def test_get_to_many_relationship_self_link(self):
        url = '/authors/{}/relationships/comment_set'.format(self.author.id)

        response = self.client.get(url)
        expected_data = {
            'links': {'self': 'http://testserver/authors/1/relationships/comment_set'},
            'data': [{'id': str(self.second_comment.id), 'type': format_resource_type('Comment')}]
        }
        assert json.loads(response.content.decode('utf-8')) == expected_data

    def test_patch_to_one_relationship(self):
        url = '/entries/{}/relationships/blog'.format(self.first_entry.id)
        request_data = {
            'data': {'type': format_resource_type('Blog'), 'id': str(self.other_blog.id)}
        }
        response = self.client.patch(url, data=request_data)
        assert response.status_code == 200, response.content.decode()
        assert response.data == request_data['data']

        response = self.client.get(url)
        assert response.data == request_data['data']

    def test_patch_one_to_many_relationship(self):
        url = '/blogs/{}/relationships/entry_set'.format(self.first_entry.id)
        request_data = {
            'data': [{'type': format_resource_type('Entry'), 'id': str(self.first_entry.id)}, ]
        }
        response = self.client.patch(url, data=request_data)
        assert response.status_code == 200, response.content.decode()
        assert response.data == request_data['data']

        response = self.client.get(url)
        assert response.data == request_data['data']

    def test_patch_many_to_many_relationship(self):
        url = '/entries/{}/relationships/authors'.format(self.first_entry.id)
        request_data = {
            'data': [
                {
                    'type': format_resource_type('Author'),
                    'id': str(self.author.id)
                },
            ]
        }
        response = self.client.patch(url, data=request_data)
        assert response.status_code == 200, response.content.decode()
        assert response.data == request_data['data']

        response = self.client.get(url)
        assert response.data == request_data['data']

    def test_post_to_one_relationship_should_fail(self):
        url = '/entries/{}/relationships/blog'.format(self.first_entry.id)
        request_data = {
            'data': {'type': format_resource_type('Blog'), 'id': str(self.other_blog.id)}
        }
        response = self.client.post(url, data=request_data)
        assert response.status_code == 405, response.content.decode()

    def test_post_to_many_relationship_with_no_change(self):
        url = '/entries/{}/relationships/comments'.format(self.first_entry.id)
        request_data = {
            'data': [{'type': format_resource_type('Comment'), 'id': str(self.first_comment.id)}, ]
        }
        response = self.client.post(url, data=request_data)
        assert response.status_code == 204, response.content.decode()
        assert len(response.rendered_content) == 0, response.rendered_content.decode()

    def test_post_to_many_relationship_with_change(self):
        url = '/entries/{}/relationships/comments'.format(self.first_entry.id)
        request_data = {
            'data': [{'type': format_resource_type('Comment'), 'id': str(self.second_comment.id)}, ]
        }
        response = self.client.post(url, data=request_data)
        assert response.status_code == 200, response.content.decode()

        assert request_data['data'][0] in response.data

    def test_delete_to_one_relationship_should_fail(self):
        url = '/entries/{}/relationships/blog'.format(self.first_entry.id)
        request_data = {
            'data': {'type': format_resource_type('Blog'), 'id': str(self.other_blog.id)}
        }
        response = self.client.delete(url, data=request_data)
        assert response.status_code == 405, response.content.decode()

    def test_delete_relationship_overriding_with_none(self):
        url = '/comments/{}'.format(self.second_comment.id)
        request_data = {
            'data': {
                'type': 'comments',
                'id': self.second_comment.id,
                'relationships': {
                    'author': {
                        'data': None
                    }
                }
            }
        }
        response = self.client.patch(url, data=request_data)
        assert response.status_code == 200, response.content.decode()
        assert response.data['author'] is None

    def test_delete_to_many_relationship_with_no_change(self):
        url = '/entries/{}/relationships/comments'.format(self.first_entry.id)
        request_data = {
            'data': [{'type': format_resource_type('Comment'), 'id': str(self.second_comment.id)}, ]
        }
        response = self.client.delete(url, data=request_data)
        assert response.status_code == 204, response.content.decode()
        assert len(response.rendered_content) == 0, response.rendered_content.decode()

    def test_delete_one_to_many_relationship_with_not_null_constraint(self):
        url = '/entries/{}/relationships/comments'.format(self.first_entry.id)
        request_data = {
            'data': [{'type': format_resource_type('Comment'), 'id': str(self.first_comment.id)}, ]
        }
        response = self.client.delete(url, data=request_data)
        assert response.status_code == 409, response.content.decode()

    def test_delete_to_many_relationship_with_change(self):
        url = '/authors/{}/relationships/comment_set'.format(self.author.id)
        request_data = {
            'data': [{'type': format_resource_type('Comment'), 'id': str(self.second_comment.id)}, ]
        }
        response = self.client.delete(url, data=request_data)
        assert response.status_code == 200, response.content.decode()

    def test_new_comment_data_patch_to_many_relationship(self):
        entry = EntryFactory(blog=self.blog, authors=(self.author,))
        comment = CommentFactory(entry=entry)

        url = '/authors/{}/relationships/comment_set'.format(self.author.id)
        request_data = {
            'data': [{'type': format_resource_type('Comment'), 'id': str(comment.id)}, ]
        }
        previous_response = {
            'data': [
                {'type': 'comments',
                 'id': str(self.second_comment.id)
                 }
            ],
            'links': {
                'self': 'http://testserver/authors/{}/relationships/comment_set'.format(
                    self.author.id
                )
            }
        }

        response = self.client.get(url)
        assert response.status_code == 200
        assert response.json() == previous_response

        new_patched_response = {
            'data': [
                {'type': 'comments',
                 'id': str(comment.id)
                 }
            ],
            'links': {
                'self': 'http://testserver/authors/{}/relationships/comment_set'.format(
                    self.author.id
                )
            }
        }

        response = self.client.patch(url, data=request_data)
        assert response.status_code == 200
        assert response.json() == new_patched_response

        assert Comment.objects.filter(id=self.second_comment.id).exists()


class TestRelatedMixin(APITestCase):
    fixtures = ('courseterm',)

    def setUp(self):
        self.author = AuthorFactory()
        self.course = Course.objects.all()
        self.term = Term.objects.all()

    def _get_view(self, kwargs):
        factory = APIRequestFactory()
        request = Request(factory.get('', content_type='application/vnd.api+json'))
        return AuthorViewSet(request=request, kwargs=kwargs)

    def test_get_related_field_name(self):
        kwargs = {'pk': self.author.id, 'related_field': 'bio'}
        view = self._get_view(kwargs)
        got = view.get_related_field_name()
        self.assertEqual(got, kwargs['related_field'])

    def test_get_related_instance_serializer_field(self):
        kwargs = {'pk': self.author.id, 'related_field': 'bio'}
        view = self._get_view(kwargs)
        got = view.get_related_instance()
        self.assertEqual(got, self.author.bio)

    def test_get_related_instance_model_field(self):
        kwargs = {'pk': self.author.id, 'related_field': 'id'}
        view = self._get_view(kwargs)
        got = view.get_related_instance()
        self.assertEqual(got, self.author.id)

    def test_get_serializer_class(self):
        kwargs = {'pk': self.author.id, 'related_field': 'bio'}
        view = self._get_view(kwargs)
        got = view.get_serializer_class()
        self.assertEqual(got, AuthorBioSerializer)

    def test_get_serializer_class_many(self):
        kwargs = {'pk': self.author.id, 'related_field': 'entries'}
        view = self._get_view(kwargs)
        got = view.get_serializer_class()
        self.assertEqual(got, EntrySerializer)

    def test_get_serializer_comes_from_included_serializers(self):
        kwargs = {'pk': self.author.id, 'related_field': 'type'}
        view = self._get_view(kwargs)
        related_serializers = view.serializer_class.related_serializers
        delattr(view.serializer_class, 'related_serializers')
        got = view.get_serializer_class()
        self.assertEqual(got, AuthorTypeSerializer)

        view.serializer_class.related_serializers = related_serializers

    def test_get_serializer_class_raises_error(self):
        kwargs = {'pk': self.author.id, 'related_field': 'type'}
        view = self._get_view(kwargs)
        self.assertRaises(NotFound, view.get_serializer_class)

    def test_retrieve_related_single(self):
        url = reverse('author-related', kwargs={'pk': self.author.pk, 'related_field': 'bio'})
        resp = self.client.get(url)
        expected = {
            'data': {
                'type': 'authorBios', 'id': str(self.author.bio.id),
                'relationships': {
                    'author': {'data': {'type': 'authors', 'id': str(self.author.id)}}},
                'attributes': {
                    'body': str(self.author.bio.body)
                },
            }
        }
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), expected)

    def test_retrieve_related_many(self):
        entry = EntryFactory(authors=self.author)
        url = reverse('author-related', kwargs={'pk': self.author.pk, 'related_field': 'entries'})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(isinstance(resp.json()['data'], list))
        self.assertEqual(len(resp.json()['data']), 1)
        self.assertEqual(resp.json()['data'][0]['id'], str(entry.id))

    def test_retrieve_related_None(self):
        kwargs = {'pk': self.author.pk, 'related_field': 'first_entry'}
        url = reverse('author-related', kwargs=kwargs)
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'data': None})

    # the following test reproduces/confirms the fix for this bug:
    # https://github.com/django-json-api/django-rest-framework-json-api/issues/489
    def test_term_related_course(self):
        """
        confirm that the related child data references the parent
        """
        term_id = self.term.first().pk
        kwargs = {'pk': term_id, 'related_field': 'course'}
        url = reverse('term-related', kwargs=kwargs)
        with mock.patch('rest_framework_json_api.views.RelatedMixin.override_pk_only_optimization',
                        True):
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        dja_response = resp.json()
        back_reference = dja_response['data']['relationships']['terms']['data']
        self.assertIn({"type": "terms", "id": str(term_id)}, back_reference)

        # the following raises AttributeError:
        with self.assertRaises(AttributeError) as ae:
            with mock.patch(
                    'rest_framework_json_api.views.RelatedMixin.override_pk_only_optimization',
                    False):
                resp = self.client.get(url)
        self.assertIn('`PKOnlyObject`', ae.exception.args[0])


class TestValidationErrorResponses(TestBase):
    def test_if_returns_error_on_empty_post(self):
        view = views.BlogViewSet.as_view({'post': 'create'})
        response = self._get_create_response("{}", view)
        self.assertEqual(400, response.status_code)
        expected = [{
            'detail': 'Received document does not contain primary data',
            'status': '400',
            'source': {'pointer': '/data'}
        }]
        self.assertEqual(expected, response.data)

    def test_if_returns_error_on_missing_form_data_post(self):
        view = views.BlogViewSet.as_view({'post': 'create'})
        response = self._get_create_response('{"data":{"attributes":{},"type":"blogs"}}', view)
        self.assertEqual(400, response.status_code)
        expected = [{
            'status': '400',
            'detail': 'This field is required.',
            'source': {'pointer': '/data/attributes/name'}
        }]
        self.assertEqual(expected, response.data)

    def test_if_returns_error_on_bad_endpoint_name(self):
        view = views.BlogViewSet.as_view({'post': 'create'})
        response = self._get_create_response('{"data":{"attributes":{},"type":"bad"}}', view)
        self.assertEqual(409, response.status_code)
        expected = [{
            'detail': (
                "The resource object's type (bad) is not the type that constitute the collection "
                "represented by the endpoint (blogs)."
            ),
            'source': {'pointer': '/data'},
            'status': '409'
        }]
        self.assertEqual(expected, response.data)

    def _get_create_response(self, data, view):
        factory = RequestFactory()
        request = factory.post('/', data, content_type='application/vnd.api+json')
        user = self.create_user('user', 'pass')
        force_authenticate(request, user)
        return view(request)


class TestModelViewSet(TestBase):
    def setUp(self):
        self.author = Author.objects.create(name='Super powerful superhero', email='i.am@lost.com')
        self.blog = Blog.objects.create(name='Some Blog', tagline="It's a blog")

    def test_no_content_response(self):
        url = '/blogs/{}'.format(self.blog.pk)
        response = self.client.delete(url)
        assert response.status_code == 204, response.rendered_content.decode()
        assert len(response.rendered_content) == 0, response.rendered_content.decode()


class TestBlogViewSet(APITestCase):

    def setUp(self):
        self.blog = Blog.objects.create(
            name='Some Blog',
            tagline="It's a blog"
        )
        self.entry = Entry.objects.create(
            blog=self.blog,
            headline='headline one',
            body_text='body_text two',
        )

    def test_get_object_gives_correct_blog(self):
        url = reverse('entry-blog', kwargs={'entry_pk': self.entry.id})
        resp = self.client.get(url)
        expected = {
            'data': {
                'attributes': {'name': self.blog.name},
                'id': '{}'.format(self.blog.id),
                'links': {'self': 'http://testserver/blogs/{}'.format(self.blog.id)},
                'meta': {'copyright': 2018},
                'relationships': {'tags': {'data': []}},
                'type': 'blogs'
            },
            'meta': {'apiDocs': '/docs/api/blogs'}
        }
        got = resp.json()
        self.assertEqual(got, expected)


class TestEntryViewSet(APITestCase):

    def setUp(self):
        self.blog = Blog.objects.create(
            name='Some Blog',
            tagline="It's a blog"
        )
        self.first_entry = Entry.objects.create(
            blog=self.blog,
            headline='headline two',
            body_text='body_text two',
        )
        self.second_entry = Entry.objects.create(
            blog=self.blog,
            headline='headline two',
            body_text='body_text two',
        )
        self.maxDiff = None

    def test_get_object_gives_correct_entry(self):
        url = reverse('entry-featured', kwargs={'entry_pk': self.first_entry.id})
        resp = self.client.get(url)
        expected = {
            'data': {
                'attributes': {
                    'bodyText': self.second_entry.body_text,
                    'headline': self.second_entry.headline,
                    'modDate': self.second_entry.mod_date,
                    'pubDate': self.second_entry.pub_date
                },
                'id': '{}'.format(self.second_entry.id),
                'meta': {'bodyFormat': 'text'},
                'relationships': {
                    'authors': {'data': [], 'meta': {'count': 0}},
                    'blog': {
                        'data': {
                            'id': '{}'.format(self.second_entry.blog_id),
                            'type': 'blogs'
                        }
                    },
                    'blogHyperlinked': {
                        'links': {
                            'related': 'http://testserver/entries/{}'
                                       '/blog'.format(self.second_entry.id),
                            'self': 'http://testserver/entries/{}'
                                    '/relationships/blog_hyperlinked'.format(self.second_entry.id)
                        }
                    },
                    'comments': {
                        'data': [],
                        'meta': {'count': 0}
                    },
                    'commentsHyperlinked': {
                        'links': {
                            'related': 'http://testserver/entries/{}'
                                       '/comments'.format(self.second_entry.id),
                            'self': 'http://testserver/entries/{}/relationships'
                                    '/comments_hyperlinked'.format(self.second_entry.id)
                        }
                    },
                    'featuredHyperlinked': {
                        'links': {
                            'related': 'http://testserver/entries/{}'
                                       '/featured'.format(self.second_entry.id),
                            'self': 'http://testserver/entries/{}/relationships'
                                    '/featured_hyperlinked'.format(self.second_entry.id)
                        }
                    },
                    'suggested': {
                        'data': [{'id': '1', 'type': 'entries'}],
                        'links': {
                            'related': 'http://testserver/entries/{}'
                                       '/suggested/'.format(self.second_entry.id),
                            'self': 'http://testserver/entries/{}'
                                    '/relationships/suggested'.format(self.second_entry.id)
                        }
                    },
                    'suggestedHyperlinked': {
                        'links': {
                            'related': 'http://testserver/entries/{}'
                                       '/suggested/'.format(self.second_entry.id),
                            'self': 'http://testserver/entries/{}/relationships'
                                    '/suggested_hyperlinked'.format(self.second_entry.id)
                        }
                    },
                    'tags': {'data': []}},
                'type': 'posts'
            }
        }
        got = resp.json()
        self.assertEqual(got, expected)
