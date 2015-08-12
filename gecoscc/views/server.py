#
# Copyright 2015, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amacias@yahoo.es>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import logging
import time
import httplib
import urllib2
import json


from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound, HTTPMethodNotAllowed
from pyramid.security import forget
from pyramid.threadlocal import get_current_registry

from deform import ValidationFailure

from gecoscc import messages
from gecoscc.i18n import gettext as _


logger = logging.getLogger(__name__)

def _getCPULoad():
    try:
        fd = file("/proc/stat", "r")
        line = fd.readline()
        fd.close()
    except Exception, e:
        logger.error("getCPULoad %s"%(str(e)))
        return (0.0, 0.0)
    
    
    values = line.strip().replace("  ", " ").split(" ")
    
    load = float(values[1]) + float(values[2]) + float(values[3])
    total = load + float(values[4])
    
    return (load, total)

def getCPULoad():
    (load1, total1) = _getCPULoad()
    time.sleep(1)
    (load2, total2) = _getCPULoad()

    if total2 - total1 == 0:
        return 0.0
        
    return ((load2 - load1) / (total2 - total1))
    
    
def parseProcFile(filename_):
    try:
        fd = file(filename_, "r")
        lines = fd.readlines()
        fd.close()
    except Exception, e:
        logger.error("parseProcFile %s"%(str(e)))
        return {}
    
    infos = {}
    for line in lines:
        line = line.strip()
        if not ":" in line:
            continue
        
        k,v = line.split(":", 1)
        infos[k.strip()] = v.strip()
    
    return infos
	
def getCPUInfos():
    infos = parseProcFile("/proc/cpuinfo")
    
    try:
        name = infos["model name"]
        nb = int(infos["processor"]) + 1
        
    except Exception, e:
        Logger.error("getCPUInfos %s"%(str(e)))
        return (1, "Unknown")
    
    return (nb, name)
	
def _getMeminfo():
    try:
        fd = file("/proc/meminfo", "r")
        lines = fd.readlines()
        fd.close()
    except Exception, e:
        Logger.error("_getMeminfo %s"%(str(e)))
        return {}
    
    infos = {}
    for line in lines:
        line = line.strip()
        if not ":" in line:
            continue
        
        k,v = line.split(":", 1)
        
        v = v.strip()
        if " " in v:
            v,_ = v.split(" ", 1)
        
        infos[k.strip()] = v.strip()
    
    return infos
	

def getRAMUsed():
    infos = _getMeminfo()
    
    try:
        total = int(infos["MemTotal"])
        free = int(infos["MemFree"])
        cached = int(infos["Cached"])
        buffers = int(infos["Buffers"])
    except Exception, e:
        Logger.warn("getRAMUsed: %s"%(str(e)))
        return 0.0
    
    return total - (free + cached + buffers)
	
	

def getRAMTotal():
    infos = _getMeminfo()
    
    try:
        total = int(infos["MemTotal"])
    
    except Exception, e:
        Logger.warn("getRAMTotal: %s"%(str(e)))
        return 0.0
    
    return total
    
    
def getJSON(url):
    obj = None
    req = urllib2.Request(url)
    try:
        stream = urllib2.urlopen(req, timeout=5)
        
        if not stream.headers.has_key("Content-Type"):
            return None
        
        contentType = stream.headers["Content-Type"]
        if ";" in contentType:
            contentType = contentType.split(";")[0]
        if not contentType == "application/json":
            logger.error("getJSON: content type: %s"%(contentType))
            return None
        
        content = stream.read()
        # logger.debug('getJSON: content: %s'%(content))
        obj = json.loads(content)
        
    except IOError, e:
        logger.warning("getJSON: error"+str(e))
        return None
    except httplib.BadStatusLine, err:
        logger.warning("getJSON: not receive HTTP response"+str(err))
        return None
    
    return obj    

def getServerStatus(ip_address):
    return getJSON('http://%s/server/internal_status'%(ip_address))
    

@view_config(route_name='internal_server_status', renderer='json')
def internal_server_status(context, request):
    # Get the status of this server
    server_status = {}
    server_status['cpu'] = {}
    server_status['cpu']['load'] = getCPULoad()
    cpuinfo = getCPUInfos()
    server_status['cpu']['name'] = cpuinfo[1]
    server_status['cpu']['ncores'] = cpuinfo[0]
    
    server_status['ram'] = {}
    server_status['ram']['total'] = getRAMTotal()
    server_status['ram']['used'] = getRAMUsed()
    
    

    return server_status


@view_config(route_name='server_status', renderer='templates/server/status.jinja2',
             permission='is_superuser')
def server_status(context, request):
    # Delete a non existent server?
    server_name = request.GET.get('delete', None)
    if server_name:
        request.db.servers.remove({"name": server_name})
    

    server_list = request.db.servers.find().sort('name')
    server_status = []
    
    # Get status of each server
    for server in server_list:
        status = getServerStatus(server['address'])
        if status is None:
            status = {}
            status['cpu'] = {}
            status['cpu']['load'] = 0
            status['cpu']['name'] = 'UNKNOWN'
            status['cpu']['ncores'] = 0
            
            status['ram'] = {}
            status['ram']['total'] = 0
            status['ram']['used'] = 0
            
        status['name'] = server['name']
        status['address'] = server['address']
        
        server_status.append(status)

    return {'server_status': server_status}


