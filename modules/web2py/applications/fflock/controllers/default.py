# -*- coding: utf-8 -*-
### required - do no delete

import sys
sys.path.append('/mnt/hgfs/fflock/')
from modules import fflock_globals
from modules import fflock_utility


def user(): return dict(form=auth())
def download(): return response.download(request,db)
def call(): return service()
### end requires
def index():
    servers = []
    _db = fflock_utility.dbconnect()
    serverstatecursor = _db.cursor()
    serverstatecursor.execute("SELECT UUID, ServerType, State FROM Servers")
    serverstateresults = serverstatecursor.fetchall()
    for server in serverstateresults:
        servers.append(server[1])
    output = fflock_globals.DATABASE_HOST
    return dict(message=servers)

def error():
    return dict()
