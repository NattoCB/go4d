"""Exercise the actual local HTTP boundary and its game state."""

import http.client
import json
import importlib.util
import threading
import unittest

class HTTPGameTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("app"), "Local game server is not implemented")
        from app import make_server
        self.server = make_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        body = json.dumps(data).encode() if data is not None else None
        request_headers = {"Content-Type": "application/json"} if body is not None else {}
        request_headers.update(headers or {})
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = response.read()
        status = response.status
        kind = response.getheader("Content-Type", "")
        connection.close()
        return status, json.loads(payload) if "application/json" in kind else payload

    def action(self, action, revision, **kwargs):
        return self.request("POST", "/api/action", {"action": action, "revision": revision, **kwargs})

    def test_move_readback_and_undo(self):
        status, before = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        status, after = self.action("move", before["revision"], point=[0, 0, 0, 0])
        self.assertEqual(status, 200)
        self.assertEqual(after["game"]["board"][0], 1)
        self.assertEqual(after["game"]["turn"], 2)
        self.assertEqual(self.request("GET", "/api/state")[1], after)
        status, restored = self.action("undo", after["revision"])
        self.assertEqual(status, 200)
        self.assertEqual(restored["game"]["board"], before["game"]["board"])

    def test_old_revision_rejected_without_second_move(self):
        self.action("move", 0, point=[0, 0, 0, 0])
        status, conflict = self.action("move", 0, point=[1, 0, 0, 0])
        self.assertEqual(status, 409)
        self.assertEqual(conflict["state"]["game"]["move_number"], 1)

    def test_illegal_move_is_atomic(self):
        _, after = self.action("move", 0, point=[0, 0, 0, 0])
        status, error = self.action("move", after["revision"], point=[0, 0, 0, 0])
        self.assertEqual(status, 400)
        self.assertEqual(error["state"], after)

    def test_demo_last_liberty_is_in_fourth_dimension(self):
        status, demo = self.action("demo", 0)
        self.assertEqual(status, 200)
        status, captured = self.action("move", demo["revision"], point=[1, 1, 1, 2])
        self.assertEqual(status, 200)
        self.assertEqual(captured["game"]["board"][40], 0)
        self.assertEqual(captured["game"]["captures"]["black"], 1)

    def test_save_import_restores_replay_and_undo(self):
        self.action("move", 0, point=[0, 0, 0, 0])
        _, saved = self.request("GET", "/api/export")
        _, fresh = self.action("new", 1, size=4, mode="local", komi=1.5)
        status, loaded = self.request("POST", "/api/import", {"revision": fresh["revision"], "data": saved})
        self.assertEqual(status, 200)
        self.assertEqual(loaded["game"]["size"], 3)
        self.assertEqual(loaded["game"]["board"][0], 1)
        _, undone = self.action("undo", loaded["revision"])
        self.assertEqual(sum(undone["game"]["board"]), 0)

    def test_ai_replies_and_undo_returns_to_human_turn(self):
        _, start = self.action("new", 0, size=3, mode="ai", komi=0.5)
        status, played = self.action("move", start["revision"], point=[0, 0, 0, 0])
        self.assertEqual(status, 200)
        self.assertEqual(played["game"]["move_number"], 2)
        self.assertEqual(played["game"]["turn"], 1)
        _, undone = self.action("undo", played["revision"])
        self.assertEqual(undone["game"]["move_number"], 0)
        self.assertEqual(sum(undone["game"]["board"]), 0)

    def test_hint_does_not_change_state(self):
        _, initial = self.request("GET", "/api/state")
        status, hinted = self.action("hint", 0)
        self.assertEqual(status, 200)
        self.assertEqual(len(hinted["hint"]), 4)
        self.assertEqual(hinted["revision"], initial["revision"])
        self.assertEqual(self.request("GET", "/api/state")[1], initial)

    def test_ai_action_limit_rejects_entire_round_before_human_move(self):
        session = self.server.session
        for _ in range(999):
            session.game.pass_turn()
            session.game.pass_turn()
            session.game.resume()
        session.game.play((0, 0, 0, 0))
        session.game.play((2, 2, 2, 2))
        session.mode = "ai"
        before = session.state()
        status, error = self.action("move", 0, point=[1, 1, 1, 1])
        self.assertEqual(status, 400)
        self.assertEqual(error["state"], before)

    def test_imported_white_start_cannot_undo_into_unplayable_ai_turn(self):
        from engine import Game, WHITE
        saved = {"format": "go4d-session-v1", "mode": "ai", "game": Game(turn=WHITE).export_data()}
        status, opened = self.request("POST", "/api/import", {"revision": 0, "data": saved})
        self.assertEqual(status, 200)
        self.assertEqual(opened["game"]["turn"], 1)
        status, rejected = self.action("undo", opened["revision"])
        self.assertEqual(status, 400)
        self.assertEqual(rejected["state"], opened)

    def test_two_passes_finish_and_resume_allows_play(self):
        _, first = self.action("pass", 0)
        _, finished = self.action("pass", first["revision"])
        self.assertTrue(finished["game"]["finished"])
        _, resumed = self.action("resume", finished["revision"])
        self.assertFalse(resumed["game"]["finished"])
        self.assertEqual(self.action("move", resumed["revision"], point=[0, 0, 0, 0])[0], 200)

    def test_bad_new_and_import_preserve_game(self):
        _, initial = self.request("GET", "/api/state")
        for fields in ({"size": True}, {"size": 19}, {"komi": float("nan")}, {"mode": "online"}):
            status, result = self.action("new", 0, **fields)
            self.assertEqual(status, 400)
            self.assertEqual(result["state"], initial)
        status, result = self.request("POST", "/api/import", {"revision": 0, "data": {"format": "wrong"}})
        self.assertEqual(status, 400)
        self.assertEqual(result["state"], initial)

    def test_foreign_origin_and_host_rejected(self):
        status, _ = self.request("POST", "/api/action", {"action": "pass", "revision": 0}, {"Origin": "https://elsewhere.example"})
        self.assertEqual(status, 403)
        status, _ = self.request("GET", "/api/state", headers={"Host": "elsewhere.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.request("GET", "/api/state")[1]["revision"], 0)

    def test_non_json_and_array_payload_rejected(self):
        self.assertEqual(self.request("POST", "/api/action", [], {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/action", ["pass"])[0], 400)

    def test_only_known_static_assets_are_served(self):
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/../engine.py")[0], 404)
        self.assertEqual(self.request("GET", "/engine.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
