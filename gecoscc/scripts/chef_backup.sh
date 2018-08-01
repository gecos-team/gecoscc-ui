#!/bin/bash
#
# Backup Chef Server
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
[[ $# -ne 2 ]] && echo "Illegal number of parameters" && exit 1

# knife-ec-backup plugin execution
# Params:
#   -s, --server-url URL             Chef Server URL
#   --webui-key			     Used to set the path to the WebUI Key. If your chef server is in a different machine,
#                                    please, copy /etc/opscode/webui_priv.pem to this server and point this path to the file

$KNIFE_BIN ec backup $1 -y -s $2 --webui-key /etc/opscode/webui_priv.pem
