# -*- coding: utf-8 -*-
### required - do no delete

import sys
import os
sys.path.append(os.path.abspath('./../../'))
from modules import fflock_globals
from modules import fflock_utility


def user(): return dict(form=auth())
def download(): return response.download(request,db)
def call(): return service()
### end requires

def index():
    return dict(message="Index")

def submit():
    servers = []
    try:
        _db = fflock_utility.dbconnect()
    except:
        return dict(message="Cannot connect to database.")

    serverstatecursor = _db.cursor()
    serverstatecursor.execute("SELECT UUID, ServerType, State FROM Servers")
    serverstateresults = serverstatecursor.fetchall()
    for server in serverstateresults:
        servers.append(server[1])
    output = fflock_globals.DATABASE_HOST

    form = FORM(TABLE(TR("Job Type:", SELECT('Transcode', 'Custom', _name="sure", requires=IS_IN_SET(['Transcode', 'Custom']))),
                    TR("Input:", INPUT(_type="text", _name="input", requires=IS_NOT_EMPTY())),
                    TR("Output", INPUT(_type="text", _name="output", requires=IS_NOT_EMPTY())),
                    TR("Compare Frame Count", INPUT(_type="checkbox", _name="framecount")),
                    TR("Encoder", SELECT('ffmpeg', 'ffmbc', 'avconv', _name="encoder", requires=IS_IN_SET(['ffmpeg', 'ffmbc', 'avconv']))),

                    TR("", INPUT(_type="submit", _value="SUBMIT"))))

    if form.accepts(request, session):
        response.flash = "form accepted"
    elif form.errors:
        response.flash = "form is invalid"
    else:
        response.flash = "please fill the form"

    return dict(form=form, vars=form.vars, message=servers)


def status():
    return dict(message="status")


def manage():
    return dict(message="manage")


def help():
    return dict(message="help")


def error():
    return dict()
