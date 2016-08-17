
import json
import common.access
import common.profile

from tornado.gen import coroutine, Return

from access import ProfileAccessModel
from common.profile import ProfileError
from common.model import Model

__author__ = "desertkun"


class NoSuchProfileError(Exception):
    pass


class ProfilesModel(Model):
    TIME_CREATED = "@time_created"
    TIME_UPDATED = "@time_updated"

    def __init__(self, db, access):
        self.db = db
        self.access = access

    def get_setup_tables(self):
        return ["account_profiles"]

    def get_setup_db(self):
        return self.db

    @coroutine
    def delete_profile(self, gamespace_id, account_id):
        yield self.db.execute(
            """
                DELETE FROM `account_profiles`
                WHERE `account_id`=%s AND `gamespace_id`=%s;
            """, account_id, gamespace_id)

    @coroutine
    def get_profile_data(self, gamespace_id, account_id, path):

        profile = UserProfile(
            self.db,
            gamespace_id,
            account_id)

        try:
            data = yield profile.get_data(path)
        except common.profile.NoDataError:
            raise NoSuchProfileError()

        raise Return(data)

    @coroutine
    def get_profile_me(self, gamespace_id, account_id, path):
        
        profile_data = yield self.get_profile_data(gamespace_id, account_id, path)

        if not path:
            # if the path is not specified, get them all
            valid_keys = yield self.access.validate_access(
                gamespace_id,
                profile_data.keys(),
                ProfileAccessModel.READ)

            result = {
                key: profile_data[key]
                for key in valid_keys
            }
        else:

            key = path[0]
            valid_keys = yield self.access.validate_access(
                gamespace_id,
                [key],
                ProfileAccessModel.READ)

            if valid_keys:
                result = profile_data
            else:
                result = None

        raise Return(result)

    @coroutine
    def get_profile_others(self, gamespace_id, account_id, path):
        
        profile_data = yield self.get_profile_data(gamespace_id, account_id, path)

        if not path:
            # if the path is not specified, get them all
            valid_keys = yield self.access.validate_access(
                gamespace_id,
                profile_data.keys(),
                ProfileAccessModel.READ_OTHERS)

            result = {
                key: profile_data[key]
                for key in valid_keys
            }
        else:
            key = path[0]
            valid_keys = yield self.access.validate_access(
                gamespace_id,
                [key],
                ProfileAccessModel.READ_OTHERS)

            if valid_keys:
                result = profile_data
            else:
                result = None

        raise Return(result)

    @coroutine
    def get_profiles(self, gamespace_id, action, account_ids, profile_fields):

        @coroutine
        def get_private():

            result = {}

            for account_id in account_ids:
                data = (yield self.get_profile_data(gamespace_id, account_id, [])) or {}

                if profile_fields:
                    result[account_id] = {
                        field: (data[field])
                        for field in profile_fields if field in data
                    }
                else:
                    result[account_id] = data

            raise Return(result)

        @coroutine
        def get_public():

            if profile_fields:
                valid_fields = yield self.access.validate_access(
                    gamespace_id,
                    profile_fields,
                    ProfileAccessModel.READ_OTHERS)
            else:
                access = yield self.access.get_access(gamespace_id)
                valid_fields = access.get_public()

            result = {}

            for account_id in account_ids:
                try:
                    data = (yield self.get_profile_data(gamespace_id, account_id, []))
                except NoSuchProfileError:
                    data = {}
                result[account_id] = {
                    field: (data[field])
                    for field in valid_fields if field in data
                }

            raise Return(result)

        actions = {
            "get_private": get_private,
            "get_public": get_public
        }

        if action not in actions:
            raise ProfileError("No such profile action: " + action)

        if len(account_ids) > 1000:
            raise ProfileError("Maximum account limit exceeded (1000).")

        profiles = yield actions[action]()

        raise Return(profiles)

    @coroutine
    def set_profile_data(self, gamespace_id, account_id, fields, path, merge=True):

        profile = UserProfile(
            self.db,
            gamespace_id,
            account_id)

        try:
            result = yield profile.set_data(
                fields,
                path,
                merge=merge)

        except common.profile.FuncError as e:
            raise ProfileError("Failed to update profie: " + e.message)

        raise Return(result)

    @coroutine
    def set_profile_me(self, gamespace_id, account_id, fields, path, merge=True):

        if not path:
            yield self.access.validate_access(
                gamespace_id,
                fields.keys(),
                ProfileAccessModel.WRITE)

            result = yield self.set_profile_data(gamespace_id, account_id, fields, path, merge=merge)
        else:
            key = path[0]
            yield self.access.validate_access(
                gamespace_id,
                [key],
                ProfileAccessModel.WRITE)

            result = yield self.set_profile_data(gamespace_id, account_id, fields, path, merge=merge)

        raise Return(result)

    @coroutine
    def set_profile_rw(self, gamespace_id, account_id, fields, path, merge=True):

        result = yield self.set_profile_data(gamespace_id, account_id, fields, path, merge=merge)

        raise Return(result)


class UserProfile(common.profile.DatabaseProfile):
    @staticmethod
    def __encode_profile__(profile):
        return json.dumps(profile)

    def __init__(self, db, gamespace_id, account_id):
        super(UserProfile, self).__init__(db)
        self.gamespace_id = gamespace_id
        self.account_id = account_id

    @staticmethod
    def __parse_profile__(profile):
        return profile

    @staticmethod
    def __process_dates__(profile):
        if ProfilesModel.TIME_CREATED not in profile:
            profile[ProfilesModel.TIME_CREATED] = common.access.utc_time()

        profile[ProfilesModel.TIME_UPDATED] = common.access.utc_time()

    @coroutine
    def get(self):
        user = yield self.conn.get(
            """
                SELECT `payload`
                FROM `account_profiles`
                WHERE `account_id`=%s AND `gamespace_id`=%s
                FOR UPDATE;
            """, self.account_id, self.gamespace_id)

        if user:
            raise Return(UserProfile.__parse_profile__(user["payload"]))

        raise common.profile.NoDataError()

    @coroutine
    def insert(self, data):
        UserProfile.__process_dates__(data)
        data = UserProfile.__encode_profile__(data)

        yield self.conn.insert(
            """
                INSERT INTO `account_profiles`
                (`account_id`, `gamespace_id`, `payload`)
                VALUES (%s, %s, %s);
            """, self.account_id, self.gamespace_id, data)

    @coroutine
    def update(self, data):
        UserProfile.__process_dates__(data)
        encoded = UserProfile.__encode_profile__(data)
        yield self.conn.execute(
            """
                UPDATE `account_profiles`
                SET `payload`=%s
                WHERE `account_id`=%s AND `gamespace_id`=%s;
            """, encoded, self.account_id, self.gamespace_id)
