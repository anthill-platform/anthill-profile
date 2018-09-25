
from anthill.common.options import options
from anthill.common import server, database, access

from . model.profile import ProfilesModel
from . model.access import ProfileAccessModel
from . import handler as h
from . import options as _opts
from . import admin


class ProfileServer(server.Server):
    # noinspection PyShadowingNames
    def __init__(self):
        super(ProfileServer, self).__init__()

        self.db = database.Database(
            host=options.db_host,
            database=options.db_name,
            user=options.db_username,
            password=options.db_password)

        self.access = ProfileAccessModel(self.db)
        self.profiles = ProfilesModel(self.db, self.access)

    def get_models(self):
        return [self.access, self.profiles]

    def get_admin(self):
        return {
            "index": admin.RootAdminController,
            "access": admin.GamespaceAccessController,
            "profiles": admin.ProfilesController,
            "profile": admin.ProfileController,
            "query": admin.QueryProfilesController
        }

    def get_metadata(self):
        return {
            "title": "User Profiles",
            "description": "Manage the profiles of the users",
            "icon": "user"
        }

    def get_handlers(self):
        return [
            (r"/profile/me/?([\w/]*)", h.ProfileMeHandler),
            (r"/profile/([\w]+)/?([\w/]*)", h.ProfileUserHandler),
            (r"/profiles", h.MassProfileUsersHandler)
        ]

    def get_internal_handler(self):
        return h.InternalHandler(self)


if __name__ == "__main__":
    stt = server.init()
    access.AccessToken.init([access.public()])
    server.start(ProfileServer)
