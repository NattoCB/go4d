"""Expose the shared rules through a transport-neutral browser API."""
from session import GameSession, RequestError


class BrowserSession:
    """Keep one independent game per browser worker."""

    def __init__(self):
        self.session = GameSession()

    def request(self, path, data):
        try:
            if path == '/api/state':
                result = self.session.state()
            elif path == '/api/export':
                result = self.session.export()
            elif path == '/api/action':
                if not isinstance(data, dict):
                    raise RequestError('请求必须是一个 JSON 对象。')
                result = self.session.action(data)
            elif path == '/api/import':
                if not isinstance(data, dict):
                    raise RequestError('请求必须是一个 JSON 对象。')
                result = self.session.import_save(data)
            else:
                raise RequestError('接口不存在。', 404)
            return 200, result
        except (RequestError, ValueError) as exc:
            return getattr(exc, 'status', 400), {'error': str(exc), 'state': self.session.state()}
