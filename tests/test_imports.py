import sys
from nzgrocery.foodstuffs import FINGERPRINT_USER, request_json

def test_no_browser_dependencies():
    assert "playwright" not in sys.modules
    assert "curl_cffi" not in sys.modules
    assert FINGERPRINT_USER == "nz-grocery-prices"
    assert callable(request_json)
