
import common.handler
import common.access
import json

from tornado.gen import coroutine, Return
from tornado.web import HTTPError

from common.access import scoped, internal
from common.internal import InternalError
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


class ProfileMeHandler(common.handler.AuthenticatedHandler):
    @coroutine
    @scoped(scopes=["profile"])
    def get(self, path):

        profiles = self.application.profiles

        account_id = self.current_user.token.account

        gamespace_id = self.current_user.token.get(
            common.access.AccessToken.GAMESPACE)

        path = filter(bool, path.split("/")) if path is not None else None

        try:
            profile = yield profiles.get_profile_me(gamespace_id, account_id, path)

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
            fields = json.loads(self.get_argument("data"))
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
            fields = json.loads(self.get_argument("data"))
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
