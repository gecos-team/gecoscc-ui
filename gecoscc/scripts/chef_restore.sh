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

# Pathname for knife executable command. Please, make sure it is correct
#KNIFE_BIN=/opt/opscode/bin/knife
KNIFE_BIN=/opt/chef/bin/knife 

# Checking number of arguments
[[ $# -ne  4 ]] && echo "Illegal number of parameters" && exit 1

# knife-ec-backup plugin execution
# Params:
#   -s, --server-url URL             Chef Server URL
#   -u, --user USER                  API Client Username
#   -k, --key KEY                    API Client Key

$KNIFE_BIN ec restore $1 -y -s $2 -u $3 -k $4
