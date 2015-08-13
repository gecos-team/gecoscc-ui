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
import sys
import traceback
import socket


from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound, HTTPMethodNotAllowed
from pyramid.security import forget
from pyramid.threadlocal import get_current_registry

from deform import ValidationFailure

from gecoscc import messages
from gecoscc.i18n import gettext as _
from gecoscc.utils import getURLComponents

from xmlrpclib import ServerProxy, ProtocolError


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
    return getJSON('http://%s/internal/server/status'%(ip_address))

def getServerConnections(ip_address):
    return getJSON('http://%s/internal/server/connections'%(ip_address))

    
def get_supervisord_url(ip_address):
    settings = get_current_registry().settings
    port = settings.get('supervisord.port')
    user = settings.get('supervisord.user')
    password = settings.get('supervisord.password')
    
    if port is None:
        logger.error("server_log: Bad configuration, please set supervisord.port in gecoscc.ini")
        return None        

    if user is None:
        logger.error("server_log: Bad configuration, please set supervisord.user in gecoscc.ini")
        return None        

    if password is None:
        logger.error("server_log: Bad configuration, please set supervisord.password in gecoscc.ini")
        return None        
        
    
    return 'http://%s:%s@%s:%s/RPC2'%(user, password, ip_address, port)

@view_config(route_name='internal_server_status', renderer='json', permission='view')
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

def _hex2dec(s):
    return str(int(s,16))

def _ip(s):
    ip = [(_hex2dec(s[6:8])),(_hex2dec(s[4:6])),(_hex2dec(s[2:4])),(_hex2dec(s[0:2]))]
    return '.'.join(ip)

def _convert_ip_port(array):
    host,port = array.split(':')
    return _ip(host),_hex2dec(port)
    
def _remove_empty(array):
    return [x for x in array if x !='']    
    
@view_config(route_name='internal_server_connections', renderer='json', permission='view')
def internal_server_connections(context, request):
    # Prepare the connection filter
    settings = get_current_registry().settings
    filter = []
    
    chef_url = settings.get('chef.url')
    chef_url_comp = getURLComponents(chef_url)
    
    chef_filter = {}
    chef_filter['name'] = 'chef'
    chef_filter['remote_host'] = socket.gethostbyname(chef_url_comp['host_name'])
    chef_filter['remote_port'] = chef_url_comp['port']
    logger.debug("internal_server_connections: chef filter: %s:%s"%(chef_filter['remote_host'], chef_filter['remote_port']))
    filter.append(chef_filter)

    mongo_uri = settings.get('mongo_uri')
    mongo_url_comp = getURLComponents(mongo_uri)
    mongo_filter = {}
    mongo_filter['name'] = 'mongo'
    mongo_filter['remote_host'] = socket.gethostbyname(mongo_url_comp['host_name'])
    mongo_filter['remote_port'] = mongo_url_comp['port']
    logger.debug("internal_server_connections: mongo filter: %s:%s"%(mongo_filter['remote_host'], mongo_filter['remote_port']))
    filter.append(mongo_filter)
    
    
    # Get the connection list of this server
    STATE = {
        '01':'ESTABLISHED',
        '02':'SYN_SENT',
        '03':'SYN_RECV',
        '04':'FIN_WAIT1',
        '05':'FIN_WAIT2',
        '06':'TIME_WAIT',
        '07':'CLOSE',
        '08':'CLOSE_WAIT',
        '09':'LAST_ACK',
        '0A':'LISTEN',
        '0B':'CLOSING'
        }
    
    server_connections = []
    
    try:
        fd = file("/proc/net/tcp", "r")
        line = fd.readline() # Skip the first line
        line = fd.readline()
        while line is not None:
            line_array = _remove_empty(line.split(' '))     # Split lines and remove empty spaces.
            if len(line_array) < 10:
                break
            l_host,l_port = _convert_ip_port(line_array[1]) # Convert ipaddress and port from hex to decimal.
            r_host,r_port = _convert_ip_port(line_array[2]) 
            #tcp_id = line_array[0]
            state = STATE[line_array[3]]
            #uid = pwd.getpwuid(int(line_array[7]))[0]       # Get user from UID.
            #inode = line_array[9]                           # Need the inode to get process pid.
            
            for f in filter:
                if r_host == f['remote_host'] and r_port == f['remote_port']:
                    connection = {}
                    connection['remote_service'] = f['name']
                    connection['local_host'] = l_host
                    connection['local_port'] = l_port
                    connection['remote_host'] = r_host
                    connection['remote_port'] = r_port
                    connection['state'] = state
                    
                    server_connections.append(connection)
            
            line = fd.readline()
            
        fd.close()
    except Exception, e:
        logger.error("internal_server_connections %s"%(str(e)))
        logger.error("Traceback: %s"%(traceback.format_exc()))
        return (0.0, 0.0)
    

    return server_connections    
    
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

@view_config(route_name='server_connections', renderer='templates/server/connections.jinja2',
             permission='is_superuser')
def server_connections(context, request):
    # Get the name of the server
    server_name = request.GET.get('server', None)
    if server_name is None:
        logger.error("server_log: server name is mandatory")
        return {'server_name': "ERROR: Unknown server", 'connections': []}
        
    server = request.db.servers.find_one({'name': server_name})
    if server is None:
        logger.error("server_log: can't find server by server name: %s"%(server_name))
        return {'server_name': "ERROR: Unknown server", 'connections': []}
        
    ip_address = server['address']
    
    # Get the connections of the server
    connections = getServerConnections(server['address'])

    return {'server_name': server_name, 'connections': connections}
    

@view_config(route_name='server_log', renderer='templates/server/log.jinja2', permission='is_superuser')
def server_log(context, request):
    # Get the name of the server
    server_name = request.GET.get('server', None)
    if server_name is None:
        logger.error("server_log: server name is mandatory")
        return None
        
    server = request.db.servers.find_one({'name': server_name})
    if server is None:
        logger.error("server_log: can't find server by server name: %s"%(server_name))
        return None
        
    ip_address = server['address']
        
    # Get the process name and number of bytes
    process_name = request.GET.get('process', None)
    nbytes = request.GET.get('bytes', 0)
    
    # Get the process list and status of that server
    supervisor_url = get_supervisord_url(ip_address)
    if supervisor_url is None:
        # Bad configuration
        return { 'server_name': 'BAD CONFIGURATION!', 
            'process_name': 'BAD CONFIGURATION!', 
            'nbytes': 0, 
            'process_info': [], 
            'log_data': 'BAD CONFIGURATION!' }
        
    supervisord = ServerProxy(supervisor_url)

    process_info = None
    try:
        process_info = supervisord.supervisor.getAllProcessInfo()
    except IOError as e:
        logger.error("server_log: error getting process info: %s"%(str(e)))
        # Connection error?
        return { 'server_name': 'ERROR(%s) %s'%(e.errno, e.strerror), 
            'process_name': 'ERROR(%s) %s'%(e.errno, e.strerror), 
            'nbytes': 0, 
            'process_info': [], 
            'log_data': 'ERROR(%s) %s'%(e.errno, e.strerror) }

    except ProtocolError as e:
        logger.error("server_log: error getting process info: %s"%(str(e)))
        # Connection error?
        return { 'server_name': 'ERROR(%s) %s'%(e.errcode, e.errmsg), 
            'process_name': 'ERROR(%s) %s'%(e.errcode, e.errmsg), 
            'nbytes': 0, 
            'process_info': [], 
            'log_data': 'ERROR(%s) %s'%(e.errcode, e.errmsg) }
            
    except: # catch *all* exceptions
        e = sys.exc_info()[0]
        logger.error("server_log: error getting process info: %s"%(str(e)))
        logger.error("Traceback: %s"%(traceback.format_exc()))
        
        # Unknown error?
        return { 'server_name': 'ERROR: %s'%(str(e)), 
            'process_name': 'ERROR: %s'%(str(e)), 
            'nbytes': 0, 
            'process_info': [], 
            'log_data': 'ERROR: %s'%(str(e)) }
    
    # Check if the process_name is in the list of processes
    if process_name is not None:
        if ":" in process_name:
            parts = process_name.split(':')
            found = False
            for p in process_info:
                if p['name'] == parts[1] and p['group'] == parts[0]:
                    found = True
                    break
                    
            if not found:
                logger.warning("server_log: Invalid process_name! (%s)"%(process_name))
                process_name = None
                
        else:
            process_name = None
    
    log_data = ''
    if process_name is not None:
        # Get the log of that process
        logger.debug("server_log: process_name: %s"%(process_name))
        try:
            log_data = supervisord.supervisor.readProcessStdoutLog(process_name, -int(nbytes), 0)
        except: # catch *all* exceptions
            e = sys.exc_info()[0]
            logger.error("server_log: error getting process log: %s"%(str(e)))
            logger.error("Traceback: %s"%(traceback.format_exc()))
            
            # Unknown error?
            return { 'server_name': 'ERROR: %s'%(str(e)), 
                'process_name': 'ERROR: %s'%(str(e)), 
                'nbytes': 0, 
                'process_info': [], 
                'log_data': 'ERROR: %s'%(str(e)) }            
    else:
        logger.debug("server_log: NO process_name!")
        process_name = 'supervisord'
        # Get the main supervisor log
        try:
            log_data = supervisord.supervisor.readMainLog(-int(nbytes), 0)
        except: # catch *all* exceptions
            e = sys.exc_info()[0]
            logger.error("server_log: error getting the main log: %s"%(str(e)))
            logger.error("Traceback: %s"%(traceback.format_exc()))
            
            # Unknown error?
            return { 'server_name': 'ERROR: %s'%(str(e)), 
                'process_name': 'ERROR: %s'%(str(e)), 
                'nbytes': 0, 
                'process_info': [], 
                'log_data': 'ERROR: %s'%(str(e)) }            

    
    return { 'server_name': server_name, 'process_name':process_name, 'nbytes':nbytes, 'process_info': process_info, 'log_data': log_data }

