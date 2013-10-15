#!/usr/bin/python

import globals
import MySQLdb
import socket
import urllib2
import sys
import os
import uuid
import re
import subprocess
from subprocess import PIPE, Popen
from re import search
from urllib2 import urlopen


def dbconnect():
    """


    @rtype : db pointer
    @return:
    """
    try:
        db = MySQLdb.connect(host=globals.DATABASE_HOST, user=globals.DATABASE_USER, passwd=globals.DATABASE_PASSWD, port=int(globals.DATABASE_PORT), db=globals.DATABASE_NAME)
    except MySQLdb.Error, e:
        print "Error %d: %s" % (e.args[0], e.args[1])
        sys.exit(1)
    return db


def local_ip_address():
    """



    @rtype : text
    @return:
    """
    # determine local IP address
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("gmail.com", 80))
    localip = s.getsockname()[0]
    s.close()
    return localip


def public_ip_address():
    """



    @rtype : text
    @return:
    """
    # determine public IP address
    publicip = urllib2.urlopen('http://ip.42.pl/raw').read()

    #data = str(urlopen('http://checkip.dyndns.com/').read())
    #publicip = re.compile(r'Address: (\d+\.\d+\.\d+\.\d+)').search(data).group(1)
    return publicip


def ping(address):
    """


    @rtype : integer
    @param address:
    @return: retval - latency determined by ping
    """
    try:
        ping_output = subprocess.Popen(["ping", "-n", "-c 3", address], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, error = ping_output.communicate()
        if out:
            try:
                packet = int(re.findall(r"(\d+) received", out)[0])
                avg = int(re.findall(r"mdev = (\d+)", out)[0])
                retval = avg
                if packet < 2:
                    retval = 9999
            except:
                retval = 9999
        else:
            retval = 9999

    except subprocess.CalledProcessError:
        retval = 9999

    return retval


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def get_uuid():
    """



    @rtype : text
    @return:
    """
    return uuid.uuid1()


def getFps(file):
    """


    @rtype : integer
    @param file:
    @return:
    """
    information = Popen(("ffmpeg", "-i", file), stdout=PIPE, stderr=PIPE)
    #fetching tbr (1), but can also get tbn (2) or tbc (3)
    #examples of fps syntax encountered is 30, 30.00, 30k
    fpsSearch = search("(\d+\.?\w*) tbr, (\d+\.?\w*) tbn, (\d+\.?\w*) tbc", information.communicate()[1])
    return fpsSearch.group(1)


def getTotalFrames(file, fps):
    """


    @rtype : integer
    @param file:
    @param fps:
    @return:
    """
    information = Popen(("ffmpeg", "-i", file), stdout=PIPE, stderr=PIPE)
    timecode = search("(\d+):(\d+):(\d+)\.(\d+)", information.communicate()[1])
    return ((((float(timecode.group(1)) * 60) + float(timecode.group(2))) * 60) + float(timecode.group(3)) + float(timecode.group(4))/100) * float(fps)


def get_storage_nfs_folder_path(storageuuid):
    db = dbconnect()
    cursor2 = db.cursor()
    cursor2.execute("SELECT LocalPathNFS, PublicPathNFS FROM Storage WHERE UUID = %s", storageuuid)
    result2 = cursor2.fetchone()
    nfsmountpath = result2[0].split(':', 1)[-1]
    return nfsmountpath


def check_dependencies(jobuuid):
    """



    @rtype : boolean
    @return:
    """
    dependencies_cleared = 1
    db = dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT UUID, JobType, JobSubType, Command, CommandOptions, JobInput, JobOutput, StorageUUID, Priority, Dependencies, MasterUUID, Assigned, State, AssignedServerUUID FROM Jobs WHERE UUID = %s", jobuuid)
    results = cursor.fetchone()
    dependencies = results[9]
    dependency_list = dependencies.split(",")
    depcursor = db.cursor()
    for dep_jobuuid in dependency_list:
        depcursor.execute("SELECT State FROM Jobs WHERE UUID = %s", dep_jobuuid)
        depresult = depcursor.fetchone()
        if depresult[0] != 2:
            dependencies_cleared = 0
            print "Dependent Job ", dep_jobuuid, " not finished - waiting."
    db.close()
    return dependencies_cleared


def remove_dependency_jobs(jobuuid):
    """



    @rtype : boolean
    @return:
    """
    db = dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT UUID, JobType, JobSubType, Command, CommandOptions, JobInput, JobOutput, StorageUUID, Priority, Dependencies, MasterUUID, Assigned, State, AssignedServerUUID FROM Jobs WHERE UUID = %s", jobuuid)
    results = cursor.fetchone()
    dependencies = results[9]
    dependency_list = dependencies.split(",")
    depcursor = db.cursor()
    for dep_jobuuid in dependency_list:
        depcursor.execute("DELETE FROM Jobs WHERE UUID = %s", dep_jobuuid)
        # remove intermediate job output files

    db.close()
    return True