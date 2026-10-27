"""Exercise the browser bridge using the same session rules as the server."""
import unittest


class BrowserSessionTests(unittest.TestCase):
    def setUp(self):
        from web_session import BrowserSession
        self.session = BrowserSession()

    def test_move_save_load_and_undo(self):
        status, before = self.session.request('/api/state', None)
        self.assertEqual(status, 200)
        status, after = self.session.request('/api/action', {'action': 'move', 'revision': before['revision'], 'point': [0, 0, 0, 0]})
        self.assertEqual(status, 200)
        self.assertEqual(after['game']['board'][0], 1)
        status, saved = self.session.request('/api/export', None)
        self.assertEqual(status, 200)
        status, restored = self.session.request('/api/import', {'revision': after['revision'], 'data': saved})
        self.assertEqual(status, 200)
        self.assertEqual(restored['game']['board'][0], 1)
        status, undone = self.session.request('/api/action', {'action': 'undo', 'revision': restored['revision']})
        self.assertEqual(status, 200)
        self.assertEqual(undone['game']['board'][0], 0)

    def test_rejects_stale_revision_and_preserves_state(self):
        self.session.request('/api/action', {'action': 'move', 'revision': 0, 'point': [0, 0, 0, 0]})
        status, result = self.session.request('/api/action', {'action': 'move', 'revision': 0, 'point': [1, 0, 0, 0]})
        self.assertEqual(status, 409)
        self.assertEqual(result['state']['game']['move_number'], 1)

    def test_fourth_dimension_demo_captures(self):
        _, demo = self.session.request('/api/action', {'action': 'demo', 'revision': 0})
        status, after = self.session.request('/api/action', {'action': 'move', 'revision': demo['revision'], 'point': [1, 1, 1, 2]})
        self.assertEqual(status, 200)
        self.assertEqual(after['game']['captures']['black'], 1)
