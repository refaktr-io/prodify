import json
from unittest.mock import patch

import stats
import usage


def test_record_increments_total_and_today_atomically():
    with patch.object(usage, 'TABLE', 'usage-table'), patch.object(usage, '_ddb') as ddb, \
         patch.object(usage, '_today', return_value='2026-09-12'):
        usage.record('conversions')
    keys = [c.kwargs['Key']['pk']['S'] for c in ddb.update_item.call_args_list]
    assert keys == ['total', 'day#2026-09-12']
    for c in ddb.update_item.call_args_list:
        assert c.kwargs['TableName'] == 'usage-table'
        assert c.kwargs['UpdateExpression'] == 'ADD #e :n'
        assert c.kwargs['ExpressionAttributeNames'] == {'#e': 'conversions'}
        assert c.kwargs['ExpressionAttributeValues'] == {':n': {'N': '1'}}


def test_record_is_noop_without_table_or_for_unknown_event():
    with patch.object(usage, 'TABLE', ''), patch.object(usage, '_ddb') as ddb:
        usage.record('conversions')
    ddb.update_item.assert_not_called()
    with patch.object(usage, 'TABLE', 't'), patch.object(usage, '_ddb') as ddb:
        usage.record('not-an-event')
    ddb.update_item.assert_not_called()


def test_record_never_raises():
    with patch.object(usage, 'TABLE', 't'), patch.object(usage, '_ddb') as ddb:
        ddb.update_item.side_effect = RuntimeError('dynamo down')
        usage.record('uploads')  # must not propagate


def test_snapshot_reads_totals_and_today():
    def get_item(TableName, Key):
        if Key['pk']['S'] == 'total':
            return {'Item': {'pk': {'S': 'total'}, 'uploads': {'N': '42'}, 'conversions': {'N': '30'}}}
        return {}
    with patch.object(usage, 'TABLE', 't'), patch.object(usage, '_ddb') as ddb, \
         patch.object(usage, '_today', return_value='2026-09-12'):
        ddb.get_item.side_effect = get_item
        snap = usage.snapshot()
    assert snap == {
        'total': {'uploads': 42, 'conversions': 30, 'rejected': 0},
        'today': {'uploads': 0, 'conversions': 0, 'rejected': 0},
        'date': '2026-09-12',
    }


def test_stats_handler_returns_json_with_cors_and_cache_headers():
    with patch.object(usage, 'snapshot', return_value={'total': {'conversions': 7}}):
        resp = stats.handler({}, None)
    assert resp['statusCode'] == 200
    assert json.loads(resp['body']) == {'total': {'conversions': 7}}
    assert resp['headers']['Access-Control-Allow-Origin'] == '*'
    assert resp['headers']['Cache-Control'].startswith('public')
