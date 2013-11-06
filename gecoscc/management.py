import imp
import pkgutil
import sys
from os.path import dirname, join
from optparse import OptionParser
import textwrap
from pyramid.paster import bootstrap


COMMANDS_PATH = join(dirname(__file__), 'commands')


def main():
    """
    This is the command which call to another scripts
    with the correct environment
    """
    usage = "usage: %prog development.ini help"

    if len(sys.argv) < 3:
        print usage
        return 2

    if sys.argv[2] == "help":
        # List all scripts
        print "help"
        for _, name, _ in pkgutil.iter_modules([COMMANDS_PATH]):
            print name
    else:
        config_uri = sys.argv[1]
        command_name = sys.argv[2]
        commandmod = imp.load_module(
            "command",
            *imp.find_module(command_name, [COMMANDS_PATH])
        )
        command = commandmod.Command(config_uri)
        command()


class BaseCommand(object):
    description = """\
    "example command"
    'example_comand deployment.ini'
    """

    usage = "usage: %prof config_uri command options"

    option_list = []

    required_options = ()

    def __init__(self, config_uri):
        self.parser = OptionParser(
            usage=self.usage,
            description=textwrap.dedent(self.description),
            option_list=self.option_list
        )

        self.options, self.args = self.parser.parse_args(sys.argv[2:])

        self.env = bootstrap(config_uri)
        self.settings = self.env["registry"].settings
        self.pyramid = self.env["request"]
        self.db = self.pyramid.db

        self.closer = self.env['closer']

    def __call__(self):
        errors = []
        for option in self.required_options:
            if getattr(self.options, option, None) is None:
                errors.append("{0} is a required option".format(option))
        if errors:
            print '\n'.join(errors)
            self.parser.print_help()
            sys.exit(1)

        self.command()
        self.closer()

    def command(self):
        raise NotImplementedError("Command not implemented")
