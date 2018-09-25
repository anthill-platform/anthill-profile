
from anthill.common import handler, access
from tornado.web import HTTPError

from anthill.common.access import scoped, internal
from anthill.common.internal import InternalError
from anthill.common.validate import validate_value, ValidationError

from . model.profile import NoSuchProfileError, ProfileError, ProfileQueryError
from . model.access import AccessDenied

import ujson


class InternalHandler(object):
    def __init__(self, application):
        self.application = application

    async def mass_profiles(self, action, gamespace, accounts, profile_fields=None):

        profiles_data = self.application.profiles

        try:
            profiles = await profiles_data.get_profiles(gamespace, action, [str(account) for account in accounts],
                                                        profile_fields or [])
        except ProfileError as e:
            raise InternalError(400, "Failed to get profiles: " + e.message)
        else:
            return profiles

    async def update_profile(self, gamespace_id, account_id, fields, path="", merge=True):

        profiles = self.application.profiles

        path = filter(bool, path.split("/")) if path is not None else None

        if not isinstance(fields, dict):
            raise InternalError(400, "Expected 'data' field to be an object (a set of fields).")

        try:
            result = await profiles.set_profile_rw(
                gamespace_id,
                account_id,
                fields,
                path,
                merge=merge)

        except ProfileError as e:
            raise InternalError(400, e.message)
        except AccessDenied as e:
            raise InternalError(403, str(e))
        else:
            return result

    async def get_my_profile(self, gamespace_id, account_id, path=""):
        profiles = self.application.profiles

        path = list(filter(bool, path.split("/"))) if path is not None else None

        try:
            result = await profiles.get_profile_me(
                gamespace_id,
                account_id,
                path)

        except ProfileError as e:
            raise InternalError(400, e.message)
        except NoSuchProfileError:
            raise InternalError(404, "No profile found")
        except AccessDenied as e:
            raise InternalError(403, str(e))
        else:
            return result

    async def get_profile_others(self, gamespace_id, account_id, path=""):
        profiles = self.application.profiles

        path = filter(bool, path.split("/")) if path is not None else None

        try:
            result = await profiles.get_profile_others(
                gamespace_id,
                account_id,
                path)

        except ProfileError as e:
            raise InternalError(400, e.message)
        except NoSuchProfileError:
            raise InternalError(404, "No profile found")
        except AccessDenied as e:
            raise InternalError(403, str(e))
        else:
            return result

    async def query_profiles(self, gamespace_id, query, limit=1000):
        profiles = self.application.profiles

        q = profiles.profile_query(gamespace_id)
        q.filters = query
        q.limit = limit

        try:
            results, count = await q.query(count=True)
        except ProfileQueryError as e:
            raise InternalError(500, str(e))

        return {
            "results": {
                r.account: {
                    "profile": r.profile
                }
                for r in results
            },
            "total_count": count
        }


class ProfileMeHandler(handler.AuthenticatedHandler):
    @scoped(scopes=["profile"])
    async def get(self, path):

        profiles = self.application.profiles

        account_id = self.current_user.token.account

        gamespace_id = self.current_user.token.get(
            access.AccessToken.GAMESPACE)

        path = filter(bool, path.split("/")) if path is not None else None

        if self.token.has_scope("profile_private"):
            method = profiles.get_profile_data
        else:
            method = profiles.get_profile_me

        try:
            profile = await method(gamespace_id, account_id, path)

        except NoSuchProfileError:
            raise HTTPError(404, "Profile was not found.")
        except AccessDenied:
            raise HTTPError(403, "Access denied")
        else:
            self.dumps(profile)

    @scoped(scopes=["profile_write"])
    async def post(self, path):

        profiles = self.application.profiles

        account_id = self.current_user.token.account

        gamespace_id = self.current_user.token.get(
            access.AccessToken.GAMESPACE)

        path = filter(bool, path.split("/")) if path is not None else None

        try:
            fields = ujson.loads(self.get_argument("data"))
        except (KeyError, ValueError):
            raise HTTPError(400, "Corrupted 'data' field: expecting JSON object.")

        if not isinstance(fields, dict):
            raise HTTPError(400, "Expected 'data' field to be an object (a set of fields).")

        merge = self.get_argument("merge", "true") == "true"

        if self.token.has_scope("profile_private"):
            method = profiles.set_profile_rw
        else:
            method = profiles.set_profile_me

        try:
            result = await method(
                gamespace_id,
                account_id,
                fields,
                path,
                merge=merge)

        except ProfileError as e:
            raise HTTPError(400, str(e))
        except AccessDenied as e:
            raise HTTPError(403, str(e))
        else:
            self.dumps(result)


class ProfileUserHandler(handler.AuthenticatedHandler):
    @scoped(scopes=["profile"])
    async def get(self, account_id, path):

        profiles = self.application.profiles

        gamespace_id = self.current_user.token.get(access.AccessToken.GAMESPACE)

        path = filter(bool, path.split("/")) if path is not None else None

        try:
            profile = await profiles.get_profile_others(gamespace_id, account_id, path)

        except NoSuchProfileError:
            raise HTTPError(404, "Profile was not found.")
        else:
            self.dumps(profile)

    @internal
    async def post(self, account_id, path):

        profiles = self.application.profiles

        gamespace_id = self.current_user.token.get(access.AccessToken.GAMESPACE)

        path = filter(bool, path.split("/")) if path is not None else None

        try:
            fields = ujson.loads(self.get_argument("data"))
        except (KeyError, ValueError):
            raise HTTPError(400, "Corrupted 'data' field: expecting JSON object.")

        if not isinstance(fields, dict):
            raise HTTPError(400, "Expected 'data' field to be an object (a set of fields).")

        merge = self.get_argument("merge", True)

        try:
            result = await profiles.set_profile_rw(gamespace_id, account_id, fields, path, merge=merge)

        except ProfileError as e:
            raise HTTPError(400, str(e))
        except AccessDenied as e:
            raise HTTPError(403, str(e))
        else:
            self.dumps(result)


class MassProfileUsersHandler(handler.AuthenticatedHandler):
    @scoped(scopes=["profile"])
    async def get(self):

        try:
            accounts = ujson.loads(self.get_argument("accounts"))
        except (KeyError, ValueError):
            raise HTTPError(400, "Corrupted 'accounts' field.")

        try:
            accounts = validate_value(accounts, "json_list_of_ints")
        except ValidationError as e:
            raise HTTPError(400, e.message)

        profile_fields = self.get_argument("profile_fields", None)

        if profile_fields:

            try:
                profile_fields = ujson.loads(profile_fields)
                profile_fields = validate_value(profile_fields, "json_list_of_strings")
            except (KeyError, ValueError, ValidationError):
                raise HTTPError(400, "Corrupted profile_fields")

        if len(accounts) > 100:
            raise HTTPError(400, "To many accounts to request.")

        profiles_data = self.application.profiles
        gamespace_id = self.current_user.token.get(access.AccessToken.GAMESPACE)

        try:
            profiles = await profiles_data.get_profiles(
                gamespace_id, "get_public", [str(account) for account in accounts],
                profile_fields or [])
        except ProfileError as e:
            raise HTTPError(400, "Failed to get profiles: " + e.message)
        else:
            self.dumps(profiles)
