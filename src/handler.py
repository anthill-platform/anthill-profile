
import common.handler
import common.access
import ujson

from tornado.gen import coroutine, Return
from tornado.web import HTTPError

from common.access import scoped, internal
from common.internal import InternalError
from common.validate import validate_value, ValidationError

from model.profile import NoSuchProfileError, ProfileError
from model.access import AccessDenied


class InternalHandler(object):
    def __init__(self, application):
        self.application = application

    @coroutine
    def mass_profiles(self, action, gamespace, accounts, profile_fields=None):

        profiles_data = self.application.profiles

        try:
            profiles = yield profiles_data.get_profiles(gamespace, action, [str(account) for account in accounts],
                                                        profile_fields or [])
        except ProfileError as e:
            raise InternalError(400, "Failed to get profiles: " + e.message)
        else:
            raise Return(profiles)

    @coroutine
    def update_profile(self, gamespace_id, account_id, fields, path="", merge=True):

        profiles = self.application.profiles

        path = filter(bool, path.split("/")) if path is not None else None

        if not isinstance(fields, dict):
            raise InternalError(400, "Expected 'data' field to be an object (a set of fields).")

        try:
            result = yield profiles.set_profile_rw(
                gamespace_id,
                account_id,
                fields,
                path,
                merge=merge)

        except ProfileError as e:
            raise InternalError(400, e.message)
        except AccessDenied as e:
            raise InternalError(403, e.message)
        else:
            raise Return(result)

    @coroutine
    def get_my_profile(self, gamespace_id, account_id, path=""):
        profiles = self.application.profiles

        path = filter(bool, path.split("/")) if path is not None else None

        try:
            result = yield profiles.get_profile_me(
                gamespace_id,
                account_id,
                path)

        except ProfileError as e:
            raise InternalError(400, e.message)
        except NoSuchProfileError:
            raise InternalError(404, "No profile found")
        except AccessDenied as e:
            raise InternalError(403, e.message)
        else:
            raise Return(result)

    @coroutine
    def get_profile_others(self, gamespace_id, account_id, path=""):
        profiles = self.application.profiles

        path = filter(bool, path.split("/")) if path is not None else None

        try:
            result = yield profiles.get_profile_others(
                gamespace_id,
                account_id,
                path)

        except ProfileError as e:
            raise InternalError(400, e.message)
        except NoSuchProfileError:
            raise InternalError(404, "No profile found")
        except AccessDenied as e:
            raise InternalError(403, e.message)
        else:
            raise Return(result)


class ProfileMeHandler(common.handler.AuthenticatedHandler):
    @coroutine
    @scoped(scopes=["profile"])
    def get(self, path):

        profiles = self.application.profiles

        account_id = self.current_user.token.account

        gamespace_id = self.current_user.token.get(
            common.access.AccessToken.GAMESPACE)

        path = filter(bool, path.split("/")) if path is not None else None

        if self.token.has_scope("profile_private"):
            method = profiles.get_profile_data
        else:
            method = profiles.get_profile_me

        try:
            profile = yield method(gamespace_id, account_id, path)

        except NoSuchProfileError:
            raise HTTPError(404, "Profile was not found.")
        except AccessDenied:
            raise HTTPError(403, "Access denied")
        else:
            self.dumps(profile)

    @coroutine
    @scoped(scopes=["profile_write"])
    def post(self, path):

        profiles = self.application.profiles

        account_id = self.current_user.token.account

        gamespace_id = self.current_user.token.get(
            common.access.AccessToken.GAMESPACE)

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
            result = yield method(
                gamespace_id,
                account_id,
                fields,
                path,
                merge=merge)

        except ProfileError as e:
            raise HTTPError(400, e.message)
        except AccessDenied as e:
            raise HTTPError(403, e.message)
        else:
            self.dumps(result)


class ProfileUserHandler(common.handler.AuthenticatedHandler):
    @coroutine
    @scoped(scopes=["profile"])
    def get(self, account_id, path):

        profiles = self.application.profiles

        gamespace_id = self.current_user.token.get(common.access.AccessToken.GAMESPACE)

        path = filter(bool, path.split("/")) if path is not None else None

        try:
            profile = yield profiles.get_profile_others(gamespace_id, account_id, path)

        except NoSuchProfileError:
            raise HTTPError(404, "Profile was not found.")
        else:
            self.dumps(profile)

    @coroutine
    @internal
    def post(self, account_id, path):

        profiles = self.application.profiles

        gamespace_id = self.current_user.token.get(common.access.AccessToken.GAMESPACE)

        path = filter(bool, path.split("/")) if path is not None else None

        try:
            fields = ujson.loads(self.get_argument("data"))
        except (KeyError, ValueError):
            raise HTTPError(400, "Corrupted 'data' field: expecting JSON object.")

        if not isinstance(fields, dict):
            raise HTTPError(400, "Expected 'data' field to be an object (a set of fields).")

        merge = self.get_argument("merge", True)

        try:
            result = yield profiles.set_profile_rw(gamespace_id, account_id, fields, path, merge=merge)

        except ProfileError as e:
            raise HTTPError(400, e.message)
        except AccessDenied as e:
            raise HTTPError(403, e.message)
        else:
            self.dumps(result)


class MassProfileUsersHandler(common.handler.AuthenticatedHandler):
    @coroutine
    @scoped(scopes=["profile"])
    def get(self):

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
        gamespace_id = self.current_user.token.get(common.access.AccessToken.GAMESPACE)

        try:
            profiles = yield profiles_data.get_profiles(
                gamespace_id, "get_public", [str(account) for account in accounts],
                profile_fields or [])
        except ProfileError as e:
            raise HTTPError(400, "Failed to get profiles: " + e.message)
        else:
            self.dumps(profiles)
