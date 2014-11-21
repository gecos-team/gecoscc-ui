from gecoscc.tests_utils import PolicyAddCommand


class Command(PolicyAddCommand):
    description = """
        test add policy package to ou
    """
    usage = ("usage: %prog test_add_policy_package_to_ou"
             "--organisational-unit-id 1234567890abcdef12345678"
             "--gecoscc-url http://localhost --gecoscc-username admin --gecoscc-password admin")

    policy_slug = "package_res"
    policy_data = {"pkgs_to_remove": [], "package_list": ["gimp"]}
    error = 'the package_list is not ["gimp"]'

    def get_policy_attr_to_check(self, policy):
        return '%s.package_list' % policy['path']

    def check_node(self, policy_attr_to_check, node):
        return node.attributes.get_dotted(policy_attr_to_check) == ["gimp"]
