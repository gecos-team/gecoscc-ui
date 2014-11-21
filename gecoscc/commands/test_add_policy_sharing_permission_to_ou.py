from gecoscc.tests_utils import PolicyAddCommand


class Command(PolicyAddCommand):
    description = """
        test add sharing permission to ou
    """
    usage = ("usage: %prog test_add_policy_sharing_permission_to_ou"
             "--organisational-unit-id 1234567890abcdef12345678"
             "--gecoscc-url http://localhost --gecoscc-username admin --gecoscc-password admin")

    policy_slug = "folder_sharing_res"
    error = '/%s: the folder_sharing_res is not true'
    policy_data = {"can_share": True}

    def get_policy_attr_to_check(self, policy, user):
        return '%s.users.%s.can_share' % (policy['path'], user['name'])

    def check_node(self, policy_attr_to_check, node):
        return node.attributes.get_dotted(policy_attr_to_check) is True
