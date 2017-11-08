
from common.options import options

import common.server
import common.database
import common.access
import common.sign
import common.keyvalue

from model.profile import ProfilesModel
from model.access import ProfileAccessModel

import admin
import handler
import options as _opts


class ProfileServer(common.server.Server):
    # noinspection PyShadowingNames
    def __init__(self):
        super(ProfileServer, self).__init__()

        self.db = common.database.Database(
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
            "profile": admin.ProfileController
        }

    def get_metadata(self):
        return {
            "title": "User profiles",
            "description": "Manage the profiles of the users",
            "icon": "user"
        }

    def get_handlers(self):
        return [
            (r"/profile/me/?([\w/]*)", handler.ProfileMeHandler),
            (r"/profile/([\w]+)/?([\w/]*)", handler.ProfileUserHandler),
            (r"/profiles", handler.MassProfileUsersHandler)
        ]

    def get_internal_handler(self):
        return handler.InternalHandler(self)


if __name__ == "__main__":
    stt = common.server.init()
    common.access.AccessToken.init([common.access.public()])
    common.server.start(ProfileServer)
