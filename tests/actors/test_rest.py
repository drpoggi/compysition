import unittest

from compysition.actors.rest import RESTTranslator
from compysition.event import HttpEvent
from compysition.testutils.test_actor import _TestActorWrapper

class TestRESTTranslator(unittest.TestCase):
    def setUp(self):
        self.actor = _TestActorWrapper(RESTTranslator("rest_translate", url_post_location='http://foo.com/bar'))

    def test_status_code_is_204_when_body_is_empty_on_get(self):
        _input = HttpEvent()
        _input.environment.update({'REQUEST_METHOD': 'GET'})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.status[0], 204)

    def test_status_message_when_body_is_empty_on_get(self):
        _input = HttpEvent()
        _input.environment.update({'REQUEST_METHOD': 'GET'})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.status[1], 'No Content')

    def test_201_status_code(self):
        _input = HttpEvent()
        _input.environment.update({'REQUEST_METHOD': 'POST'})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.status[0], 201)

    def test_201_status_message(self):
        _input = HttpEvent()
        _input.environment.update({'REQUEST_METHOD': 'POST'})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.status[1], 'Created')

    def test_status_is_200_when_body_exists_on_GET(self):
        _input = HttpEvent(data={'hello': 3})
        _input.environment.update({'REQUEST_METHOD': 'GET'})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.status[0], 200)

    def test_location_url_exists_on_post(self):
        _input = HttpEvent(data={'hello': 3})
        _input.environment.update({'REQUEST_METHOD': 'POST'})
        self.actor.input = _input
        output = self.actor.output
        self.assertIsNotNone(output.headers.get('Location'))

    def test_location_url_contains_valid_id(self):
        _input = HttpEvent(data={'hello': 3})
        _input.environment.update({'REQUEST_METHOD': 'POST'})
        self.actor.input = _input
        output = self.actor.output
        url = output.headers.get('Location')
        location_id = url.split('/')[-1]
        self.assertRegexpMatches(location_id, r'^[a-z0-9]{32}$')
