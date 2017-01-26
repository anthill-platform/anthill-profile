import common.admin as a
from common.internal import Internal, InternalError
import common.access
import json

from tornado.gen import coroutine, Return

from model.access import NoAccessData
from model.profile import ProfileError, NoSuchProfileError


class GamespaceAccessController(a.AdminController):
    @coroutine
    def get(self):

        access_data = self.application.access

        try:
            access = yield access_data.get_access(self.gamespace)
        except NoAccessData:
            access_private = ""
            access_public = ""
            access_protected = ""
        else:
            access_private = ",".join(access.get_private())
            access_public = ",".join(access.get_public())
            access_protected = ",".join(access.get_protected())

        result = {
            "access_private": access_private,
            "access_public": access_public,
            "access_protected": access_protected
        }

        raise a.Return(result)

    def render(self, data):
        return [
            a.breadcrumbs([], "Profile access"),
            a.form("Edit access to profile fields", fields={
                "access_public": a.field(
                    "Public access fields (everybody may see, owner may change them)",
                    "tags", "primary"),
                "access_private": a.field(
                    "Private access fields (server only fields, no one except server can see or change)",
                    "tags", "primary"),
                "access_protected": a.field(
                    "Protected access fields (only owner may see, only server may change)",
                    "tags", "primary")
            }, methods={
                "update": a.method("Update", "primary")
            }, data=data),
            a.links("Navigate", [
                a.link("@back", "Go back", icon="chevron-left")
            ])
        ]

    def access_scopes(self):
        return ["profile_admin"]

    @coroutine
    def update(self, access_private, access_public, access_protected):

        access_data = self.application.access

        yield access_data.set_access(self.gamespace,
                                     access_private.split(","),
                                     access_protected.split(","),
                                     access_public.split(","))

        result = {
            "access_private": access_private,
            "access_public": access_public,
            "access_protected": access_protected
        }

        raise a.Return(result)


class ProfileController(a.AdminController):
    @coroutine
    def get(self, account):

        profiles = self.application.profiles

        try:
            profile = (yield profiles.get_profile_data(self.gamespace, account, None))
        except NoSuchProfileError:
            profile = {}

        result = {
            "profile": profile
        }

        raise a.Return(result)

    def render(self, data):
        return [
            a.breadcrumbs([
                a.link("profiles", "Edit user profiles"),
            ], "@{0}".format(self.context.get("account"))),
            a.form(title="Edit account profile", fields={
                "profile": a.field("Profile", "json", "primary", "non-empty")
            }, methods={
                "update": a.method("Update", "primary")
            }, data=data),
            a.links("Navigate", [
                a.link("profiles", "Go back", icon="chevron-left")
            ])
        ]

    def access_scopes(self):
        return ["profile_admin"]

    @coroutine
    def update(self, profile):

        try:
            profile = json.loads(profile)
        except (KeyError, ValueError):
            raise a.ActionError("Corrupted profile")

        profiles = self.application.profiles
        account_id = self.context.get("account")

        try:
            yield profiles.set_profile_data(self.gamespace, account_id, profile, None, merge=False)
        except ProfileError as e:
            raise a.ActionError(e.message)

        raise a.Redirect(
            "profile",
            message="Profile has been updated",
            account=account_id)


class ProfilesController(a.AdminController):
    def render(self, data):
        return [
            a.breadcrumbs([], "Edit user profile"),
            a.split([
                a.form(title="Find by credential", fields={
                    "credential": a.field("User credential", "text", "primary", "non-empty"),
                }, methods={
                    "search_credential": a.method("Search", "primary")
                }, data=data),
                a.form(title="Find by account number", fields={
                    "account": a.field("Account number", "text", "primary", "number")
                }, methods={
                    "search_account": a.method("Search", "primary")
                }, data=data)
            ]),
            a.links("Navigate", [
                a.link("index", "Go back", icon="chevron-left")
            ])
        ]

    def access_scopes(self):
        return ["profile_admin"]
    @coroutine
    def search_account(self, account):
        raise a.Redirect("profile", account=account)


    @coroutine
    def search_credential(self, credential):

        internal = Internal()

        try:
            account = yield internal.request(
                "login",
                "get_account",
                credential=credential)

        except InternalError as e:
            if e.code == 400:
                raise a.ActionError("Failed to find credential: bad username")
            if e.code == 404:
                raise a.ActionError("Failed to find credential: no such user")

            raise a.ActionError(e.body)

        raise a.Redirect("profile", account=account["id"])


class RootAdminController(a.AdminController):
    def render(self, data):
        return [
            a.links("Profile service", [
                a.link("profiles", "Edit user profiles", icon="user"),
                a.link("access", "Edit profile access", icon="lock")
            ])
        ]

    def access_scopes(self):
        return ["profile_admin"]

