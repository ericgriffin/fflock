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
    form = FORM(TABLE(TR("Job Type:", SELECT('Transcode', 'Custom', _name="jobtype", requires=IS_IN_SET(['Transcode', 'Custom']))),
                    TR("Input:", INPUT(_type="text", _name="input", requires=IS_NOT_EMPTY())),
                    TR("Output", INPUT(_type="text", _name="output", requires=IS_NOT_EMPTY())),
                    TR("Pre-Options:", INPUT(_type="text", _name="preoptions")),
                    TR("Options", INPUT(_type="text", _name="options")),
                    TR("Encoder", SELECT('ffmpeg', 'ffmbc', 'avconv', _name="encoder", requires=IS_IN_SET(['ffmpeg', 'ffmbc', 'avconv']))),
                    TR("Compare Frame Count", INPUT(_type="checkbox", _name="framecount")),
                    TR("", INPUT(_type="submit", _value="SUBMIT"))))

    if form.accepts(request, session):
        response.flash = "form accepted"

    elif form.errors:
        response.flash = "form is invalid"
    else:
        response.flash = "please fill the form"

    return dict(form=form, vars=form.vars)


def status():
    return dict()

def status_data_servers():
    master_color = "#CCCCFF"
    storage_color = "#FFC100"
    warning_color = "#DD0000"
    slave_color = "#B4FFC7"
    busy_color = "#FF0000"
    idle_color = "#000000"

    #servers = SQLTABLE(db().select(db.Servers.ServerType, db.Servers.State), headers='fieldname:capitalize')
    #servers = SQLFORM.grid(db.Servers, searchable=False, details=False, sortable=False, csv=False, formstyle="divs")
    servers = db(db.Servers).select()
    servertable = ""
    if not db(db.Servers).isempty():
        servertable = "<table id='box-table-a'>"
        servertable += "<thead><tr><th scope='col' id='ServerType'>Server Type</th><th scope='col' id='LocalIP'>Local IP</th><th scope='col' id='LocalIP'>Public IP</th></tr></thead>"
        #servertable += "<tfoot><tr><td>...</td></tr></tfoot>"
        servertable += "<tbody>"
        for server in servers.sort(lambda server: server.ServerType):
            bgcolor = slave_color
            statecolor = idle_color
            if server.State == 1: statecolor = busy_color
            if server.ServerType == "Slave":
                bgcolor = warning_color
                connectivity = db(db.Connectivity.SlaveServerUUID == server.UUID).select()
                for connection in connectivity:
                    if connection.Connected == 1:
                        bgcolor = slave_color
            if server.ServerType == "Storage":
                bgcolor = warning_color
                storage = db(db.Storage.ServerUUID == server.UUID).select()
                for share in storage:
                    bgcolor = storage_color
            if server.ServerType == "Master":
                bgcolor = master_color
            servertable = servertable + "<tr ALIGN='left' STYLE='background:%s; color:%s; font-variant: small-caps;'>" % (bgcolor, statecolor) + "<td>" + server.ServerType + "</td><td>" + server.LocalIP + "</td><td>" + server.PublicIP + "</td></tr>"
        servertable += "</tbody></table>"
    else:
        servertable = "<div>No servers are currently running.</div>"
    return servertable

def status_data_jobs():
    #jobs = SQLTABLE(db().select(db.Jobs.JobType, db.Jobs.JobSubType, db.Jobs.JobInput, db.Jobs.JobOutput, db.Jobs.State, db.Jobs.Assigned, db.Jobs.Progress), headers='fieldname:capitalize')
    #jobs = SQLFORM.grid(db.Jobs, searchable=False, details=False, sortable=False, csv=False)
    master_color = "#CCCCFF"
    storage_color = "#FFC100"
    slave_color = "#B4FFC7"
    warning_color = "#DD0000"
    error_color = "#CC2222"
    finished_color = "#0000FF"
    busy_color = "#FF0000"
    idle_color = "#000000"

    jobs = db(db.Jobs).select()
    table = ""
    if not db(db.Jobs).isempty():
        table = "<table id='box-table-a'>"
        table += "<thead><tr><th scope='col' id='JobType'>Job Type</th><th scope='col' id='Job Sub-Type'>Sub-Type</th><th scope='col' id='Command'>Command</th></tr></thead>"
        #table += "<tfoot><tr><td>...</td></tr></tfoot>"
        table += "<tbody>"
        for job in jobs.sort(lambda job: job.JobType):
            bgcolor = slave_color
            statecolor = idle_color
            if job.State == 1: statecolor = busy_color
            elif job.State == 2: statecolor = finished_color
            elif job.State > 2: statecolor = error_color
            if job.JobType == "Master": bgcolor = master_color
            if job.JobType == "Storage": bgcolor = storage_color
            if job.JobType == "Slave": bgcolor = slave_color
            table = table + "<tr ALIGN='left' STYLE='background:%s; color:%s; font-variant: small-caps;'>" % (bgcolor, statecolor) + "<td>" + job.JobType + "</td><td>" + job.JobSubType + "</td><td>" + job.Command + "</td></tr>"
    else:
        table = "<div>No jobs currently queued.</div>"
    return table

def status_data_storage():
    storage = SQLTABLE(db().select(db.Storage.StorageType, db.Storage.LocalPathNFS, db.Storage.PublicPathNFS), headers='fieldname:capitalize')
    #storage = SQLFORM.grid(db.Storage, searchable=False, details=False, sortable=False, csv=False)
    return storage.xml()

def status_data_connectivity():
    connectivity = SQLTABLE(db().select(db.Connectivity.ALL), headers='fieldname:capitalize')
    #connectivity = SQLFORM.grid(db.Connectivity, searchable=False, details=False, sortable=False, csv=False)
    return connectivity.xml()

def manage():
    return dict(message="manage")


def help():
    return dict(message="help")


def error():
    return dict()
