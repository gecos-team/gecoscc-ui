from pkg_resources import iter_entry_points
import logging
from jsonschema import validate as json_validate

logger = logging.getLogger(__name__)


class BasePolicy(object):

    name = ''
    screen_name = ''
    _obj = None

    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "node": {"type": "string"},
        },
    }

    recipes = []

    def __init__(self, raw):
        self.validate(raw)
        self._obj = raw

    def validate(self, raw):
        return json_validate(raw, self.schema)

    def change(self, raw):
        self.validate(raw, self.schema)
        self._obj = raw

    def get_obj(self):
        return self._obj

    def get_recipes(self):
        """ Return the list of recipes involved with this policy
        """
        return self.recipes

    def translate_to_recipes(self):
        """ Return the instance values converted into chef readable format
            Not the node, but the recipes configuration
        """
        raise NotImplementedError()


class PoliciesRegistry(dict):

    def __init__(self):
        for entry_point in iter_entry_points('gecoscc.policies'):
            if entry_point.name in self:
                logger.warn("Duplicate entry point: %s" % entry_point.name)
            else:
                logger.debug("Registering entry point: %s" % entry_point.name)
                self[entry_point.name] = entry_point.load()


class PolicyDoesNotExist(Exception):
    pass


class PoliciesManager(object):

    policies = PoliciesRegistry()

    def get_policies(self):

        return [{
            'name': policy.name,
            'screen_name': policy.screen_name,
            'schema': policy.schema
        } for policy in self.policies.items() if getattr(policy, 'name', None)]

    def get_policy(self, name):

        policy = self.policies.get(name, None)
        if policy is None:
            raise PolicyDoesNotExist
        return policy
