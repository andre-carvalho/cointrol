"""
Bitcointoyou API client.

<https://www.bitcointoyou.com/API>

The client uses `tornado.httpclient` and can be used
either synchronous or asynchronous fashion.

-----

Based on:

    kmadac/bitstamp-python-client
    Copyright (c) 2013 Kamil Madac
    <https://github.com/kmadac/bitstamp-python-client/blob/master/LICENSE.txt>

And:
    
    No license defined
    https://github.com/victor-oliveira1/bitcointoyou-python3
-----

"""
from __future__ import division
import json
import time
import hmac
import hashlib
import logging
import datetime
from decimal import Decimal
from urllib.parse import urlencode

import pytz
from tornado.httpclient import AsyncHTTPClient, HTTPClient, HTTPRequest


log = logging.getLogger(__name__)

NOT_PROVIDED = object()


def parse_datetime(s):
    return datetime.datetime \
        .strptime(s.rsplit('.', 1)[0], '%Y-%m-%d %H:%M:%S') \
        .replace(tzinfo=pytz.timezone('America/Sao_Paulo'))


def parse_timestamp(n):
    naive = datetime.datetime.fromtimestamp(int(n))
    # FIXME: what timezone is it really?
    from django.utils import timezone
    tz = timezone.get_current_timezone()
    local = tz.localize(naive)
    return local


def maybe(type_):
    """Schema field type whose value can be `None` or `type_`."""

    def func(val):
        if val is not None:
            return type_(val)

    return func


class Model(dict):
    schema = {}

    def __init__(self, response):
        super().__init__()
        for key, value in response.items():
            func = self.schema.get(key, NOT_PROVIDED)
            if func is NOT_PROVIDED:
                raise ValueError('%s unknown field: %r' % (type(self), key))
            if func:
                value = func(value)
            self[key] = value

    def __getattr__(self, k):
        return self[k]

class ResponseStatus(Model):
    schema = {
        'success': Decimal,
        'oReturn': str,
        'date': parse_timestamp,
        'timestamp': parse_timestamp
    }

class Ticker(Model):
    scheme = {
        'high': Decimal,
        'low': Decimal,
        'vol': Decimal,
        'last': Decimal,
        'buy': Decimal,
        'sell': Decimal,
        'date': parse_timestamp,
    }


class Order(Model):
    schema = {
        'asset': str,
        'currency': str,
        'id': Decimal,
        'action': str,
        'status': str,
        'price': Decimal,
        'amount': Decimal,
        'executedPriceAverage': Decimal,
        'executedAmount': Decimal,
        'dateCreated': parse_timestamp
    }


class Transaction(Model):
    schema = {
        'tid': int,
        'date': parse_datetime,
        'type': int,
        'price': Decimal,
        'currency': str,
        'amount': Decimal,
    }


class Balance(Model):
    schema = {
        'BRL': Decimal,
        'BTC': Decimal,
    }

class BitcointoyouError(Exception):
    pass


class BitcointoyouClientError(BitcointoyouError):
    pass


class InvalidNonceError(BitcointoyouClientError):
    pass


class BitcointoyouClient:
    _root = 'https://www.bitcointoyou.com/API'

    def __init__(self, key=None, secret=None):
        credentials = [key, secret]
        assert all(credentials) or not any(credentials)
        self._set_auth(*credentials)
        self._requests = []

    def _set_auth(self, key, secret):
        self._key = str(key)
        self._secret = str(secret)
        self._nonce = time.strftime('%s')

    def _get_auth_params(self):

        signature = base64.b64encode(
            hmac.new(
                self._secret.encode(),
                '{}{}'.format(self._nonce, self._key).encode(),
                digestmod='sha256').digest()
            )
        params = {
            'key': self._key,
            'signature': signature,
            'nonce': self._nonce
        }
        self._nonce += 1
        return params

    """ Unused for bitcointoyou """
    """
        def _get(self, path, callback=None, params=None, model_class=None):
            if params:
                path += '?' + urlencode(params)
            return self._request('GET',
                                path=path,
                                callback=callback,
                                model_class=model_class)
    """
    def _post(self, path, callback=None, params=None, model_class=None):
        params = params or {}
        params.update(self._get_auth_params())
        body = urlencode(params)
        return self._request('POST',
                             path=path,
                             callback=callback,
                             body=body,
                             model_class=model_class)

    def _request(self, method, path, callback=None, body=None,
                 model_class=None):

        now = datetime.datetime.utcnow()
        period_start = now - datetime.timedelta(minutes=10)
        self._requests = [dt for dt in self._requests if dt >= period_start]
        self._requests.append(now)
        log.debug('%d requests in last %d seconds',
                  len(self._requests),
                  (now - self._requests[0]).seconds)
        self._requests.append(datetime.datetime.utcnow())
        client_class = AsyncHTTPClient if callback else HTTPClient
        log.debug('%s > %s %s %r', client_class.__name__, method, path, body)
        request = HTTPRequest(
            url=self._root + path,
            method=method,
            body=body,
        )
        client = client_class()
        if callback:
            return client.fetch(
                request=request,
                callback=lambda resp: callback(self._process_response(
                    resp, model_class))
            )
        else:
            return self._process_response(client.fetch(request), model_class)

    def _process_response(self, response, model_class=None):
        """
        :type response: tornado.httpclient.HTTPResponse
        """
        response.rethrow()

        model_class = model_class or Model
        log.debug('< %s %s', response.headers, response.body)

        content_type = response.headers['Content-Type']
        if 'json' not in content_type:
            raise BitcointoyouError(
                'not JSON response (%s)' % content_type,
                response.headers,
                response.body
            )

        try:
            data = json.loads(response.body.decode('utf8'))
        except (ValueError, UnicodeError) as e:
            raise BitcointoyouError(
                'could not decode response json',
                response.headers,
                response.body) from e

        if 'error' in data:
            if data['error'] == 'Invalid nonce':
                raise InvalidNonceError
            raise BitcointoyouClientError(data)

        if isinstance(data, list):
            data = list(map(model_class, data))
        else:
            data = model_class(data)

        return data

    ### Public REST API methods ###

    def ticker(self, callback=None):
        """
        Return dictionary
        """
        return self._post('/ticker/', callback=callback, model_class=Ticker)

    def order_book(self, group=True, callback=None):
        """
        Returns JSON dictionary with "bids" and "asks".
        Each is a list of open orders and each order is represented
        as a list of price and amount.

        """
        return self._post('/order_book/',
                         params={
                             'group': group
                         },
                         callback=callback)

    def transactions(self, timedelta_secs=86400, callback=None):
        """Return transactions for the last 'timedelta' seconds."""
        timedelta = datetime.datetime.utcnow() + datetime.timedelta(timedelta_secs)
        return self._post('/trades.aspx',
                         params={
                             'timestamp': timedelta,
                             'currency': 'BTC'
                         },
                         callback=callback, model_class=Transaction)

    def conversion_rate_usd_eur(self, callback=None):
        """
        Returns simple dictionary

        {'buy': 'buy conversion rate', 'sell': 'sell conversion rate'}

        """
        return self._post('/eur_usd/', callback=callback)

    ### Private REST API methods ###

    def account_balance(self, callback=None):
        """
        Returns dictionary:

        {u'btc_reserved': u'0',
         u'fee': u'0.5000',
         u'btc_available': u'2.30856098',
         u'usd_reserved': u'0',
         u'btc_balance': u'2.30856098',
         u'usd_balance': u'114.64',
         u'usd_available': u'114.64'}

        """
        return self._post('/balance/', callback=callback, model_class=Balance)

    def user_transactions(self, offset=0, limit=100,
                          descending=True, callback=None):
        """
        Returns descending list of transactions.
        Every transaction (dictionary) contains

        {u'usd': u'-39.25',
         u'datetime': u'2013-03-26 18:49:13',
         u'fee': u'0.20', u'btc': u'0.50000000',
         u'type': 2,
         u'id': 213642}
        """
        return self._post(
            '/user_transactions/',
            callback=callback,
            model_class=Transaction,
            params={
                'offset': offset,
                'limit': limit,
                'sort': 'desc' if descending else 'asc'
            }
        )

    def open_orders(self, callback=None):
        """
        Returns JSON list of open orders.
        Each order is represented as dictionary:

        """
        return self._post('/open_orders/',
                          callback=callback,
                          model_class=Order)

    def cancel_order(self, order_id, callback=None):
        """
        Cancel the order specified by order_id
        Returns True if order was successfully canceled,
        otherwise tuple (False, msg) like (False, u'Order not found')
        """
        return self._post('/cancel_order/', callback=callback, params={
            'id': order_id
        })

    def buy_limit_order(self, amount, price, callback=None):
        """
        Order to buy amount of bitcoins for specified price
        """
        return self._post(
            '/buy/',
            callback=callback,
            model_class=Order,
            params={
                'amount': amount,
                'price': price
            }
        )

    def sell_limit_order(self, amount, price, callback=None):
        """
        Order to sell amount of bitcoins for specified price
        """
        return self._post(
            '/sell/',
            callback=callback,
            model_class=Order,
            params={
                'amount': amount,
                'price': price
            }
        )

    def withdrawal_requests(self, callback=None):
        """
        Returns list of withdrawal requests.
        Each request is represented as dictionary
        """
        return self._post('/withdrawal_requests/', callback=callback)

    def bitcoin_withdrawal(self, amount, address, callback=None):
        """
        Send bitcoins to another bitcoin wallet specified by address
        """
        return self._post('/bitcoin_withdrawal/', callback=callback, params={
            'amount': amount,
            'address': address
        })

    def bitcoin_deposit_address(self, callback=None):
        """
        Returns bitcoin deposit address as unicode string
        """
        return self._post('/bitcoin_deposit_address/', callback=callback)

    def unconfirmed_bitcoin_deposits(self, callback=None):
        """
        Returns JSON list of unconfirmed bitcoin transactions.
        Each transaction is represented as dictionary:
        amount - bitcoin amount
        address - deposit address used
        confirmations - number of confirmations
        """
        return self._post('/unconfirmed_btc/', callback=callback)

    def ripple_withdrawal(self, amount, address, currency, callback=None):
        """
        Returns true if successful
        """
        return self._post('/ripple_withdrawal/', callback=callback, params={
            'amount': amount,
            'address': address,
            'currency': currency
        })

    def ripple_deposit_address(self, callback=None):
        """
        Returns ripple deposit address as unicode string
        """
        return self._post('/ripple_address/', callback=callback)
