"""Best-effort usage counters in DynamoDB.

One item per period, keyed by pk: 'total' and 'day#YYYY-MM-DD'. Each event
is a numeric attribute incremented atomically (ADD), so concurrent Lambdas
never lose counts. Counting must never break a request: failures are logged.
"""
import datetime
import os

import boto3

TABLE = os.environ.get('USAGE_TABLE', '')
EVENTS = ('uploads', 'conversions', 'rejected')

_ddb = boto3.client('dynamodb')


def _today():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')


def record(event, n=1):
    if not TABLE or event not in EVENTS:
        return
    for pk in ('total', f'day#{_today()}'):
        try:
            _ddb.update_item(
                TableName=TABLE,
                Key={'pk': {'S': pk}},
                UpdateExpression='ADD #e :n',
                ExpressionAttributeNames={'#e': event},
                ExpressionAttributeValues={':n': {'N': str(n)}},
            )
        except Exception as e:  # noqa: BLE001 - never fail the caller over a counter
            print(f"usage.record({event}) failed for {pk}: {e}")


def _counts(pk):
    item = _ddb.get_item(TableName=TABLE, Key={'pk': {'S': pk}}).get('Item', {})
    return {e: int(item.get(e, {}).get('N', 0)) for e in EVENTS}


def snapshot():
    return {'total': _counts('total'), 'today': _counts(f'day#{_today()}'), 'date': _today()}
