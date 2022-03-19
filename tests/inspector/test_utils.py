from src.inspector.utils import _SafeRunError


class TestSafeRunError:
    def test_implicitly_false(self):
        assert not _SafeRunError()
