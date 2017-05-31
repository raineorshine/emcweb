# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import time

from hashlib import md5

from flask import current_app
from flask_restful import Resource
from flask_restful import reqparse
from emcweb.emcweb_webapi.login_resource import LoginResource

from emcweb.exts import connection
from emcweb.models import Settings
from emcweb.login.models import Credentials
from emcweb.utils import apply_db_settings, CONFIGS_DB
from emcweb.emcweb_webapi.views import api
from emcweb.tasks import restart_emercoind


class SettingsAPI(LoginResource):

    @staticmethod
    def get():
        params = {
            setting.option: CONFIGS_DB[setting.option]['db2html'](setting.value)
            for setting in Settings.query.all()
            if setting.option in CONFIGS_DB.keys() and CONFIGS_DB[setting.option].get('show', True)
        }
        for key, value in CONFIGS_DB.items():
            if key not in params:
                params[key] = value['default']

        return params

    @staticmethod
    def post():
        parser = reqparse.RequestParser()
        parser.add_argument('open_time', type=int, required=False, default=None)
        parser.add_argument('lc_api_key', type=str, required=False, default=None)
        parser.add_argument('lc_secret_key', type=str, required=False, default=None)
        parser.add_argument('smtp_enabled', type=bool, required=False, default=None)
        parser.add_argument('smtp_host', type=str, required=False, default=None)
        parser.add_argument('smtp_port', type=int, required=False, default=None)
        parser.add_argument('smtp_connection', type=int, required=False, default=None)
        parser.add_argument('smtp_email', type=str, required=False, default=None)
        parser.add_argument('smtp_auth', type=int, required=False, default=None)
        parser.add_argument('smtp_username', type=str, required=False, default=None)
        parser.add_argument('smtp_password', type=str, required=False, default=None)
        args = parser.parse_args()

        for key, value in args.items():
            if value is not None:
                record = Settings.query.get(key)
                if record:
                    record.value = value
                else:
                    record = Settings(option=key, value=value)
                connection.session.add(record)

        connection.session.commit()
        apply_db_settings(current_app)

        return {'result_status': True, 'result': 'Saved'}

    @staticmethod
    def put():
        try:
            result = restart_emercoind.delay()
        except Exception:
            return {'result_status': False, 'message': 'Celery transport connection refused'}, 500
        for i in range(60):
            if result.ready():
                time.sleep(10)
                return {'result_status': True, 'result': 'Emercoind restarted'}
            time.sleep(1)

        time.sleep(10)

        return {'result_status': False, 'message': 'Celery hasn\'t reported about finish'}, 500


class PasswordAPI(Resource):

    @staticmethod
    def put():
        parser = reqparse.RequestParser()
        parser.add_argument('password', type=str, required=True, help='Need set old password')
        parser.add_argument('new_password', type=str, required=True, help='Need set new password')
        args = parser.parse_args()

        old_password = md5(args['password'].encode()).hexdigest()
        cred = Credentials.query.first()

        # verify old password
        if not cred.password == old_password:
            return {'result_status': False,
                    'message': 'Old password is invalid'}, 400
        else:
            # set new_password
            cred.password = md5(args['new_password'].encode()).hexdigest()
            connection.session.commit()

        # logout (maybe on client)
        return {'result_status': True,
                'message': 'Your password has been changed successfully'}


api.add_resource(SettingsAPI, '/settings')
api.add_resource(PasswordAPI, '/password')
