#!/bin/bash
#!/bin/bash
#
# Restore Chef Server
#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# All rights reserved - EUPL License V 1.1
# http://www.osor.eu/eupl
#

# Checking number of arguments
[[ $# -ne  4 ]] && echo "Illegal number of parameters" && exit 1

# Enable ruby environment
RBENV_ENABLE=/opt/rh/rh-ruby24/enable

. $RBENV_ENABLE

# Knife-backup plugin execution
# Params:
#   -D, --backup-directory DIR       Restore backup data from DIR
#   -s, --server-url URL             Chef Server URL
#   -u, --user USER                  API Client Username
#   -k, --key KEY                    API Client Key


knife backup restore -D $1 -y -s $2 -u $3 -k $4
