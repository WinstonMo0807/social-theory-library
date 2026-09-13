from datetime import date

import pytest

from catalog.services.publication_commands import _public_values, _same_public_value


@pytest.mark.parametrize('before,after,expected', [
    ('2000-01-01', date(2000,1,1), True),
    (date(2000,1,1), '2000-01-01', True),
    ('2000-01-01', date(2001,1,1), False),
    (None, '', True),
    ([], None, True),
    ('old', 'new', False),
])
def test_snapshot_dates_compare_to_their_public_value(before, after, expected):
    assert _same_public_value(before, after) is expected


def test_missing_legacy_publication_mode_is_document_without_mutating_snapshot():
    snapshot = {'edition': {'id':'legacy'}, 'work':{'title':'Existing book'}}
    assert _public_values(snapshot)['publication_mode'] == 'document'
    assert 'publication_mode' not in snapshot['edition']
    assert _public_values({'edition':{'publication_mode':'bibliographic'}})['publication_mode'] == 'bibliographic'
    assert 'publication_mode' not in _public_values({})
