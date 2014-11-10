import json


from gecoscc.models import AdminUser


def admin_serialize(admin):
    return json.dumps(AdminUser().serialize(admin));