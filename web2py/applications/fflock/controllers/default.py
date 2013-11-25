# -*- coding: utf-8 -*-
### required - do no delete

import sys
import os
import shutil
import gluon.contrib.simplejson
from datetime import datetime
sys.path.append(os.path.abspath('./../'))
from modules import fflock_globals
from modules import fflock_utility

master_color = "#317b80"
storage_color = "#609194"
warning_color = "#DD0000"
slave_color = "#92dce0"
busy_color = "#df1c1c"
idle_color = "#000000"
error_color = "#CC2222"
finished_color = "#28be9b"


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

    return dict(form=form, vars=form.vars)


def status():
    return dict()


def status_data_servers():

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
            serveruuid = server.UUID
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

            serverjobs = db(db.Jobs.AssignedServerUUID == serveruuid).select(orderby=~db.Jobs.CreatedTime)
            bgcolor = slave_color
            for serverjob in serverjobs:
                statecolor = idle_color
                bgcolor = slave_color
                if serverjob.State == 1: statecolor = busy_color
                elif serverjob.State == 2: statecolor = finished_color
                elif serverjob.State > 2: statecolor = error_color
                if serverjob.JobType == "Master": bgcolor = master_color
                if serverjob.JobType == "Storage": bgcolor = storage_color
                if serverjob.JobType == "Slave": bgcolor = slave_color

                servertable = servertable + "<tr  ALIGN='left' STYLE='background:%s; color:%s; font-variant: small-caps;'>" % (bgcolor, statecolor) + "<td style='padding-left:2em;'>" + serverjob.JobSubType + "</td><td nowrap='wrap' style='max-width:300px;'>" + ((str(serverjob.JobInput)[:25] + '..') if len(str(serverjob.JobInput)) > 25 else serverjob.JobInput) + "</td><td nowrap='wrap' style='max-width:300px;'>" + ((str(serverjob.JobOutput)[:25] + '..') if len(str(serverjob.JobOutput)) > 25 else serverjob.JobOutput) + "</td></tr>"

        servertable += "</tbody></table>"
    else:
        servertable = "<div>No servers are currently running.</div>"
    return servertable


def status_data_jobs():
    #jobs = SQLTABLE(db().select(db.Jobs.JobType, db.Jobs.JobSubType, db.Jobs.JobInput, db.Jobs.JobOutput, db.Jobs.State, db.Jobs.Assigned, db.Jobs.Progress), headers='fieldname:capitalize')
    #jobs = SQLFORM.grid(db.Jobs, searchable=False, details=False, sortable=False, csv=False)

    masterjobs = db(db.Jobs.JobType == "Master").select(orderby=~db.Jobs.CreatedTime)
    table = ""
    if not db(db.Jobs).isempty():
        table = "<table id='box-table-a'>"
        table += "<thead><tr><th scope='col' id='JobType'>Job Type</th><th scope='col' id='Job Sub-Type'>Action</th><th scope='col' id='Command'>Command</th></tr></thead>"
        #table += "<thead><tr><th scope='col' id='JobType'>Job Type</th><th scope='col' id='Job Sub-Type'>Sub-Type</th><th scope='col' id='Command'>Command</th></tr></thead>"
        #table += "<tfoot><tr><td>...</td></tr></tfoot>"
        table += "<tbody>"
        for masterjob in masterjobs:
            masteruuid = masterjob.UUID
            bgcolor = master_color
            statecolor = idle_color
            table = table + "<tr ALIGN='left' STYLE='background:%s; color:%s; font-variant: small-caps;'>" % (bgcolor, statecolor) + "<td>" + masterjob.JobType + "</td><td>" + masterjob.JobSubType + "</td><td>" + masterjob.Command + "</td></tr>"

            #display sub-jobs for each master job
            subjobs = db(db.Jobs.MasterUUID == masteruuid).select(orderby=~db.Jobs.CreatedTime)
            bgcolor = slave_color
            for subjob in subjobs:
                statecolor = idle_color
                bgcolor = slave_color
                if subjob.State == 1: statecolor = busy_color
                elif subjob.State == 2: statecolor = finished_color
                elif subjob.State > 2: statecolor = error_color
                if subjob.JobType == "Master": bgcolor = master_color
                if subjob.JobType == "Storage": bgcolor = storage_color
                if subjob.JobType == "Slave": bgcolor = slave_color
                table = table + "<tr  ALIGN='left' STYLE='background:%s; color:%s; font-variant: small-caps;'>" % (bgcolor, statecolor) + "<td style='padding-left:2em;'>" + subjob.JobType + "</td><td>" + subjob.JobSubType + "</td><td>" + subjob.Command + "</td></tr>"

            table =  table + "<tr><td><br><br></td><td></td><td></td></tr>"
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



def my_upload():
    import re
    fileApp = request.vars.pic
    filename = fileApp.filename.replace(' ', '')
    result=''
    http_host=''

    #Prevent special caracters in the file name
    expression = '[*+~$&^#@!;:,|]'
    regex = re.compile(expression)
    if regex.search(filename):
        result="Special caracters NO!!! Nothing to do..."
        return response.json('<div class="error_wrapper">\
            <div id="title__error" class="error" style="display: inline-block;">'\
            +result+\
            '</div></div>')
    aux = db.files.file.store(fileApp, filename)
    db.files.insert(file=aux, title=filename)

    if request.env.http_x_forwarded_host:
      http_host = request.env.http_x_forwarded_host.split(':',1)[0]
    else:
      http_host = request.env.http_host

    last = db().select(db.files.ALL)[-1]
    result=T('Successfuly! Here the link: ')
    result+="<a href=http://"+http_host+'/'+request.application+'/'+request.controller+'/download/'+last.file+">Donwload</a>"

    return response.json('<div class="alert alert-success">'\
            +result+\
            '</div>')


def jobs():
    return dict()


def jobs_data_jobs():
    masterjobs = db(db.Jobs.JobType == "Master").select(orderby=~db.Jobs.CreatedTime)
    table = ""
    if not db(db.Jobs).isempty():
        table = "<table id='box-table-a'>"
        #table += "<thead><tr><th scope='col' id='JobType'>Job Type</th><th scope='col' id='Job Sub-Type'>Sub-Type</th><th scope='col' id='Command'>Command</th></tr></thead>"
        #table += "<tfoot><tr><td>...</td></tr></tfoot>"
        table += "<tbody>"
        for masterjob in masterjobs:
            masteruuid = masterjob.UUID
            bgcolor = master_color
            statecolor = idle_color
            table = table + "<tr ALIGN='left' STYLE='background:%s; color:%s; font-variant: small-caps;'>" % (bgcolor, statecolor) + "<td>" + masterjob.JobType + "</td><td>" + masterjob.JobSubType + "</td><td>" + masterjob.Command + "</td></tr>"

            #display sub-jobs for each master job
            subjobs = db(db.Jobs.MasterUUID == masteruuid).select(orderby=~db.Jobs.CreatedTime)
            bgcolor = slave_color
            for subjob in subjobs:
                statecolor = idle_color
                bgcolor = slave_color
                if subjob.State == 1: statecolor = busy_color
                elif subjob.State == 2: statecolor = finished_color
                elif subjob.State > 2: statecolor = error_color
                if subjob.JobType == "Master": bgcolor = master_color
                if subjob.JobType == "Storage": bgcolor = storage_color
                if subjob.JobType == "Slave": bgcolor = slave_color
                table = table + "<tr  ALIGN='left' STYLE='background:%s; color:%s; font-variant: small-caps;'>" % (bgcolor, statecolor) + "<td style='padding-left:2em;'>" + subjob.JobType + "</td><td>" + subjob.JobSubType + "</td><td>" + subjob.Command + "</td></tr>"

            table =  table + "<tr><td><br><br></td><td></td><td></td></tr>"
    else:
        table = "<div>No jobs currently queued.</div>"
    return table
