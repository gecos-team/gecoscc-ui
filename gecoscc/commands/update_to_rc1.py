from gecoscc.management import BaseCommand


class Command(BaseCommand):
    description = """
        Update to the rc1
    """

    def command(self):
        db = self.pyramid.db
        db.nodes.drop_index('name_-1_type_-1')