import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from config.throttling import InternalAwareAnonRateThrottle


@pytest.mark.parametrize("case", ("first", "second"))
def test_throttle_history_is_fresh_per_test_but_enforced_within_test(case):
    class ShortAnonThrottle(InternalAwareAnonRateThrottle):
        rate = "2/min"

    request = RequestFactory().get(f"/cache-isolation/{case}/", REMOTE_ADDR="198.51.100.42")
    request.user = AnonymousUser()
    throttle = ShortAnonThrottle()

    assert throttle.allow_request(request, None) is True
    assert throttle.allow_request(request, None) is True
    assert throttle.allow_request(request, None) is False
