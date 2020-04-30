
from . access import ProfileAccessModel

from anthill.common import access, profile
from anthill.common.profile import ProfileError, FuncError, NoDataError
from anthill.common.model import Model
from anthill.common.database import DatabaseError, format_conditions_json, ConditionError

import ujson


class NoSuchProfileError(Exception):
    pass


class ProfileQueryError(Exception):
    pass


class ProfileAdapter(object):
    def __init__(self, data):
        self.account = str(data.get("account_id"))
        self.profile = data.get("payload")


class ProfileQuery(object):
    def __init__(self, gamespace_id, db):
        self.gamespace_id = gamespace_id
        self.db = db

        self.filters = None

        self.offset = 0
        self.limit = 0

    def __values__(self):
        conditions = [
            "`account_profiles`.`gamespace_id`=%s"
        ]

        data = [
            str(self.gamespace_id)
        ]

        if self.filters:
            for condition, values in format_conditions_json('payload', self.filters):
                conditions.append(condition)
                data.extend(values)

        return conditions, data

    async def query(self, one=False, count=False):
        try:
            conditions, data = self.__values__()
        except ConditionError as e:
            raise ProfileQueryError("Failed to process profile conditions: {0}".format(str(e)))

        query = """
            SELECT {0} `account_id`, `payload` FROM `account_profiles`
            WHERE {1}
        """.format(
            "SQL_CALC_FOUND_ROWS" if count else "",
            " AND ".join(conditions))

        if self.limit:
            query += """
                LIMIT %s,%s
            """

            data.append(int(self.offset))
            data.append(int(self.limit))

        query += ";"

        if one:
            try:
                result = await self.db.get(query, *data)
            except DatabaseError as e:
                raise ProfileQueryError("Failed to get profiles: " + e.args[1])

            if not result:
                return None

            return ProfileAdapter(result)
        else:
            try:
                result = await self.db.query(query, *data)
            except DatabaseError as e:
                raise ProfileQueryError("Failed to query profiles: " + e.args[1])

            count_result = 0

            if count:
                count_result = await self.db.get(
                    """
                        SELECT FOUND_ROWS() AS count;
                    """)
                count_result = count_result["count"]

            items = map(ProfileAdapter, result)

            if count:
                return items, count_result

            return items


class ProfilesModel(Model):
    TIME_CREATED = "@time_created"
    TIME_UPDATED = "@time_updated"

    # noinspection PyShadowingNames
    def __init__(self, db, access):
        self.db = db
        self.access = access

    def get_setup_tables(self):
        return ["account_profiles"]

    def get_setup_db(self):
        return self.db

    def has_delete_account_event(self):
        return True

    async def accounts_deleted(self, gamespace, accounts, gamespace_only):
        if gamespace_only:
            await self.db.execute(
                """
                    DELETE FROM `account_profiles`
                    WHERE `gamespace_id`=%s AND `account_id` IN %s;
                """, gamespace, accounts)
        else:
            await self.db.execute(
                """
                    DELETE FROM `account_profiles`
                    WHERE `account_id` IN %s;
                """, accounts)

    async def delete_profile(self, gamespace_id, account_id):
        await self.db.execute(
            """
                DELETE FROM `account_profiles`
                WHERE `account_id`=%s AND `gamespace_id`=%s;
            """, account_id, gamespace_id)

    def profile_query(self, gamespace_id):
        return ProfileQuery(gamespace_id, self.db)

    async def get_profile_data(self, gamespace_id, account_id, path):
        user_profile = UserProfile(
            self.db,
            gamespace_id,
            account_id)

        try:
            data = await user_profile.get_data(path)
        except NoDataError:
            raise NoSuchProfileError()

        return data

    async def get_profile_me(self, gamespace_id, account_id, path):
        
        profile_data = await self.get_profile_data(gamespace_id, account_id, path)

        if not path:
            # if the path is not specified, get them all
            valid_keys = await self.access.validate_access(
                gamespace_id,
                list(profile_data.keys()),
                ProfileAccessModel.READ)

            result = {
                key: profile_data[key]
                for key in valid_keys
            }
        else:

            key = path[0]
            valid_keys = await self.access.validate_access(
                gamespace_id,
                [key],
                ProfileAccessModel.READ)

            if valid_keys:
                result = profile_data
            else:
                result = None

        return result

    async def get_profile_others(self, gamespace_id, account_id, path):
        
        profile_data = await self.get_profile_data(gamespace_id, account_id, path)

        if not path:
            # if the path is not specified, get them all
            valid_keys = await self.access.validate_access(
                gamespace_id,
                list(profile_data.keys()),
                ProfileAccessModel.READ_OTHERS)

            result = {
                key: profile_data[key]
                for key in valid_keys
            }
        else:
            key = path[0]
            valid_keys = await self.access.validate_access(
                gamespace_id,
                [key],
                ProfileAccessModel.READ_OTHERS)

            if valid_keys:
                result = profile_data
            else:
                result = None

        return result

    async def get_profiles(self, gamespace_id, action, account_ids, profile_fields):

        async def get_private():

            result = {}

            for account_id in account_ids:
                data = (await self.get_profile_data(gamespace_id, account_id, [])) or {}

                if profile_fields:
                    result[account_id] = {
                        field: (data[field])
                        for field in profile_fields if field in data
                    }
                else:
                    result[account_id] = data

            return result

        async def get_public():

            if profile_fields:
                valid_fields = await self.access.validate_access(gamespace_id, profile_fields,
                                                                 ProfileAccessModel.READ_OTHERS)
            else:
                public_access = await self.access.get_access(gamespace_id)
                valid_fields = public_access.get_public()

            result = {}

            for account_id in account_ids:
                try:
                    data = (await self.get_profile_data(gamespace_id, account_id, []))
                except NoSuchProfileError:
                    data = {}
                result[account_id] = {
                    field: (data[field])
                    for field in valid_fields if field in data
                }

            return result

        actions = {
            "get_private": get_private,
            "get_public": get_public
        }

        if action not in actions:
            raise ProfileError("No such profile action: " + action)
        if len(account_ids) > 1000:
            raise ProfileError("Maximum account limit exceeded (1000).")
        profiles = await actions[action]()
        return profiles

    async def set_profile_data(self, gamespace_id, account_id, fields, path, merge=True):
        user_profile = UserProfile(self.db, gamespace_id, account_id)
        try:
            result = await user_profile.set_data(fields, path, merge=merge)
        except FuncError as e:
            raise ProfileError("Failed to update profile: " + e.message)
        return result

    async def set_profiles_data(self, gamespace_id, accounts: dict, merge=True):
        user_profiles = UserProfiles(self.db, gamespace_id, list(accounts.keys()))
        try:
            result = await user_profiles.set_data(accounts, None, merge=merge)
        except FuncError as e:
            raise ProfileError("Failed to update profiles: " + e.message)
        return result

    async def set_profile_me(self, gamespace_id, account_id, fields, path, merge=True):

        if not path:
            await self.access.validate_access(
                gamespace_id,
                list(fields.keys()),
                ProfileAccessModel.WRITE)

            result = await self.set_profile_data(gamespace_id, account_id, fields, path, merge=merge)
        else:
            key = path[0]
            await self.access.validate_access(
                gamespace_id,
                [key],
                ProfileAccessModel.WRITE)

            result = await self.set_profile_data(gamespace_id, account_id, fields, path, merge=merge)

        return result

    async def set_profile_rw(self, gamespace_id, account_id, fields, path, merge=True):
        result = await self.set_profile_data(gamespace_id, account_id, fields, path, merge=merge)
        return result

    async def set_profiles_rw(self, gamespace_id, accounts: dict, merge=True):
        result = await self.set_profiles_data(gamespace_id, accounts, merge=merge)
        return result


class UserProfile(profile.DatabaseProfile):
    # noinspection PyShadowingNames
    @staticmethod
    def __encode_profile__(profile):
        return ujson.dumps(profile)

    def __init__(self, db, gamespace_id, account_id):
        super(UserProfile, self).__init__(db)
        self.gamespace_id = gamespace_id
        self.account_id = account_id

    # noinspection PyShadowingNames
    @staticmethod
    def __parse_profile__(profile):
        return profile

    # noinspection PyShadowingNames
    @staticmethod
    def __process_dates__(profile):
        if ProfilesModel.TIME_CREATED not in profile:
            profile[ProfilesModel.TIME_CREATED] = access.utc_time()

        profile[ProfilesModel.TIME_UPDATED] = access.utc_time()

    async def get(self):
        user = await self.conn.get(
            """
                SELECT `payload`
                FROM `account_profiles`
                WHERE `account_id`=%s AND `gamespace_id`=%s
                FOR UPDATE;
            """, self.account_id, self.gamespace_id)

        if user:
            return UserProfile.__parse_profile__(user["payload"])

        raise profile.NoDataError()

    async def insert(self, data):
        UserProfile.__process_dates__(data)
        data = UserProfile.__encode_profile__(data)

        await self.conn.insert(
            """
                INSERT INTO `account_profiles`
                (`account_id`, `gamespace_id`, `payload`)
                VALUES (%s, %s, %s);
            """, self.account_id, self.gamespace_id, data)

    async def update(self, data):
        UserProfile.__process_dates__(data)
        encoded = UserProfile.__encode_profile__(data)
        await self.conn.execute(
            """
                UPDATE `account_profiles`
                SET `payload`=%s
                WHERE `account_id`=%s AND `gamespace_id`=%s;
            """, encoded, self.account_id, self.gamespace_id)


class UserProfiles(profile.DatabaseProfile):
    # noinspection PyShadowingNames
    @staticmethod
    def __encode_profile__(profile):
        return ujson.dumps(profile)

    def __init__(self, db, gamespace_id, account_ids):
        super(UserProfiles, self).__init__(db)
        self.gamespace_id = gamespace_id
        self.account_ids = account_ids

    # noinspection PyShadowingNames
    @staticmethod
    def __process_dates__(profile):
        if ProfilesModel.TIME_CREATED not in profile:
            profile[ProfilesModel.TIME_CREATED] = access.utc_time()

        profile[ProfilesModel.TIME_UPDATED] = access.utc_time()

    async def get(self):
        users = await self.conn.query(
            """
                SELECT `payload`, `account_id`
                FROM `account_profiles`
                WHERE `account_id` IN %s AND `gamespace_id`=%s
                FOR UPDATE;
            """, self.account_ids, self.gamespace_id)

        return {
            str(user["account_id"]): user["payload"]
            for user in users
        }

    async def insert(self, data):
        # not supported since get never returns NoDataError
        pass

    async def update(self, data: dict):
        for account_id, account_profile in data.items():
            UserProfiles.__process_dates__(account_profile)

        values = []
        entries = []

        for account_id, account_profile in data.items():
            values.append("(%s, %s, %s)")
            entries.extend([account_id, self.gamespace_id,
                            UserProfiles.__encode_profile__(account_profile)])

        await self.conn.execute(
            """
                REPLACE INTO `account_profiles`
                (`account_id`, `gamespace_id`, `payload`)
                VALUES {0};
            """.format(", ".join(values)), *entries)
