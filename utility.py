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
from datetime import datetime, timedelta
import boto
import boto.s3.connection
import ftplib

socket.setdefaulttimeout(12)


def dbconnect():
    """


    @rtype : db pointer
    @return:
    """
    try:
        db = MySQLdb.connect(host=globals.DATABASE_HOST, user=globals.DATABASE_USER, passwd=globals.DATABASE_PASSWD,
                             port=int(globals.DATABASE_PORT), db=globals.DATABASE_NAME)
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
    fpssearch = search("(\d+\.?\w*) tbr, (\d+\.?\w*) tbn, (\d+\.?\w*) tbc", information.communicate()[1])
    return fpssearch.group(1)


def getTotalFrames(file, fps):
    """


    @rtype : integer
    @param file:
    @param fps:
    @return:
    """
    information = Popen(("ffmpeg", "-i", file), stdout=PIPE, stderr=PIPE)
    timecode = search("(\d+):(\d+):(\d+)\.(\d+)", information.communicate()[1])
    return ((((float(timecode.group(1)) * 60) + float(timecode.group(2))) * 60) + float(timecode.group(3)) + float(
        timecode.group(4)) / 100) * float(fps)


def get_storage_nfs_folder_path(storageuuid):
    db = dbconnect()
    cursor2 = db.cursor()
    cursor2.execute("SELECT LocalPathNFS, PublicPathNFS FROM Storage WHERE UUID = '%s'" % storageuuid)
    result2 = cursor2.fetchone()
    nfsmountpath = result2[0].split(':', 1)[-1]
    db.close()
    return nfsmountpath


def check_dependencies(jobuuid):
    """



    @rtype : boolean
    @return:
    """
    dependencies_cleared = 1
    db = dbconnect()
    cursor = db.cursor()
    cursor.execute(
        "SELECT UUID, JobType, JobSubType, Command, CommandOptions, JobInput, JobOutput, StorageUUID, Priority, Dependencies, MasterUUID, Assigned, State, AssignedServerUUID FROM Jobs WHERE UUID = '%s'" % jobuuid)
    results = cursor.fetchone()
    if results is not None:
        dependencies = results[9]
        dependency_list = dependencies.split(",")
        if dependency_list is not None:
            depcursor = db.cursor()
            for dep_jobuuid in dependency_list:
                depcursor.execute("SELECT State FROM Jobs WHERE UUID = '%s'" % dep_jobuuid)
                depresult = depcursor.fetchall()
                for result in depresult:
                    if result[0] != 2:
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
    cursor.execute(
        "SELECT UUID, JobType, JobSubType, Command, CommandOptions, JobInput, JobOutput, StorageUUID, Priority, Dependencies, MasterUUID, Assigned, State, AssignedServerUUID FROM Jobs WHERE UUID = '%s'" % jobuuid)
    results = cursor.fetchone()
    dependencies = results[9]
    dependency_list = dependencies.split(",")
    depcursor = db.cursor()
    for dep_jobuuid in dependency_list:
        depcursor.execute("DELETE FROM Jobs WHERE UUID = '%s'" % dep_jobuuid)
        # remove intermediate job output files

    db.close()
    return True


def number_of_registered_slaves():
    """


    @rtype : integer
    @return:
    """
    number_of_slaves = 0
    db = dbconnect()
    cursor = db.cursor()
    slavecursor = db.cursor()
    slavecursor.execute("SELECT ServerType FROM Servers WHERE ServerType = '%s'" % "Slave")
    slaveresults = slavecursor.fetchall()
    for slaverow in slaveresults:
        number_of_slaves += 1
    db.close()
    return number_of_slaves


def number_of_connected_slaves(storageuuid):
    """


    @rtype : integer
    @return:
    """
    number_of_connected_slaves = 0
    db = dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT StorageUUID, Connected FROM Connectivity WHERE StorageUUID = '%s'" % storageuuid)
    results = cursor.fetchall()
    for row in results:
        number_of_connected_slaves += 1
    db.close()
    return number_of_connected_slaves


def find_server_storage_UUIDs(serveruuid):
    """


    @rtype : list
    @return:
    """
    storageuuids = []
    db = dbconnect()
    cursor = db.cursor()
    cursor.execute("SELECT UUID, ServerUUID FROM Storage WHERE ServerUUID = '%s'" % serveruuid)
    results = cursor.fetchall()
    for row in results:
        storageuuids.append(row[0])
    db.close()
    return storageuuids


def find_master_UUID_for_job(uuid):
    """



    @rtype : string
    @return: master uuid
    """
    db = dbconnect()
    masteruuid = ""
    cursor = db.cursor()
    cursor.execute("SELECT MasterUUID FROM Jobs WHERE UUID = '%s'" % uuid)
    results = cursor.fetchall()
    for row in results:
        masteruuid = row[0]
    db.close()
    return masteruuid


def find_job_options_for_job(uuid):
    """



    @rtype : string
    @return: master uuid
    """
    db = dbconnect()
    joboptions = ""
    cursor = db.cursor()
    cursor.execute("SELECT JobOptions FROM Jobs WHERE UUID = '%s'" % uuid)
    results = cursor.fetchall()
    for row in results:
        joboptions = row[0]
    db.close()
    return joboptions


def find_storage_UUID_for_job():
    """



    @rtype : storage uuid
    @return:
    """
    db = dbconnect()
    storageuuid = ""
    storagecursor = db.cursor()
    storagecursor.execute("SELECT UUID FROM Storage WHERE StorageType = '%s'" % "NFS")
    storageresults = storagecursor.fetchall()
    for storagerow in storageresults:
        storageuuid = storagerow[0]
    db.close()
    return storageuuid


def find_server_for_storage_job():
    """



    @rtype : storage server uuid
    @return:
    """
    db = dbconnect()
    storagecursor = db.cursor()
    storagecursor.execute("SELECT UUID, ServerType, State FROM Servers WHERE ServerType = '%s'" % "Storage")
    storageresults = storagecursor.fetchall()

    #find best slave server to assign the job
    shortest_queue = 1000000
    server_with_shortest_queue = ""
    for storagerow in storageresults:
        current_queue = 0
        storageserveruuid = storagerow[0]
        jobcursor = db.cursor()
        jobcursor.execute(
            "SELECT JobType, Assigned, State, AssignedServerUUID, Priority, Dependencies, Progress FROM Jobs WHERE AssignedServerUUID = '%s'" % str(storageserveruuid))
        jobresults = jobcursor.fetchall()
        for jobrow in jobresults:
            current_queue += 1
        if current_queue < shortest_queue:
            server_with_shortest_queue = storageserveruuid
            shortest_queue = current_queue
    db.close()
    return server_with_shortest_queue


def find_server_for_slave_job():
    """



    @rtype : slave server uuid
    @return:
    """
    db = dbconnect()
    slaveserveruuid = "NA"
    slavecursor = db.cursor()
    slavecursor.execute("SELECT UUID, ServerType, State FROM Servers WHERE ServerType = '%s'" % "Slave")
    slaveresults = slavecursor.fetchall()

    #find best slave server to assign the job
    shortest_queue = 1000000
    server_with_shortest_queue = ""
    for slaverow in slaveresults:
        current_queue = 0
        slaveserveruuid = slaverow[0]
        jobcursor = db.cursor()
        jobcursor.execute(
            "SELECT JobType, Assigned, State, AssignedServerUUID, Priority, Dependencies, Progress FROM Jobs WHERE AssignedServerUUID = '%s'" % str(
                slaveserveruuid))
        jobresults = jobcursor.fetchall()
        for jobrow in jobresults:
            current_queue += 1
        if current_queue < shortest_queue:
            server_with_shortest_queue = slaveserveruuid
            shortest_queue = current_queue
    db.close()
    return server_with_shortest_queue


def download_file_http(url, filename):
    file_name = url.split('/')[-1]
    print "Downloading", url, "to", filename
    header = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
    'Accept-Encoding': 'none',
    'Accept-Language': 'en-US,en;q=0.8',
    'Connection': 'keep-alive'}
    try:
        req = urllib2.Request(url, headers=header)
        u = urllib2.urlopen(req)
    except urllib2.URLError:
        return True
    file = open(filename, 'wb')
    meta = u.info()
    file_size = int(meta.getheaders("Content-Length")[0])
    print "Downloading: %s Bytes: %s" % (filename, file_size)

    file_size_dl = 0
    block_sz = 8192
    while True:
        buffer = u.read(block_sz)
        if not buffer:
            break

        file_size_dl += len(buffer)
        file.write(buffer)
        status = r"%10d  [%3.2f%%]" % (file_size_dl, file_size_dl * 100. / file_size)
        status = status + chr(8) * (len(status) + 1)
        print status,

    file.close()

    return True


def download_file_ftp(url, filename):
    file_name = url.split('/')[-1]
    req = urllib2.Request(url)
    u = urllib2.urlopen(req)
    file = open(filename, 'wb')

    block_sz = 8192
    while True:
        buffer = u.read(block_sz)
        if not buffer:
            break
        file.write(buffer)

    file.close()

    return True


def upload_file_ftp(source, destination):
    req = urllib2.Request(destination)
    u = urllib2.urlopen(req)
    file = open(source, 'rb')

    block_sz = 8192
    while True:
        buffer = file.read(block_sz)
        if not buffer:
            break
        u.write(buffer)

    file.close()
    return True


def download_file_s3(url, filename):
    file_name = url.split('/')[-1]
    conn = boto.connect_s3(globals.S3ID, globals.S3KEY)
    bucket = conn.get_bucket(globals.S3BUCKET)
    key = bucket.get_key(file_name)
    key.get_contents_to_filename(filename)
    return True


def upload_file_s3(source, destination):
    destination_path = destination.split('//')[-1]
    destination_path = "/" + destination_path
    file_name = source.split('//')[-1]
    conn = boto.connect_s3(globals.S3ID, globals.S3KEY)
    bucket = conn.get_bucket(globals.S3BUCKET)
    key = bucket.new_key(destination_path)

    print "Uploading to AWS S3:", destination, " source", source
    key.set_contents_from_filename(file_name)
    os.remove(source)
    return True


def submit_job(jobuuid, jobtype, jobsubtype, command, commandpreoptions, commandoptions, input, output, dependencies,
               masteruuid, joboptions):
    """


    @rtype : boolean
    @param jobtype:
    @param command:
    @param commandoptions:
    @param input:
    @param output:
    """
    db = dbconnect()
    timestamp = datetime.now()

    storageuuid = find_storage_UUID_for_job()
    assignedserveruuid = ""
    if jobtype == "Slave":
        assignedserveruuid = find_server_for_slave_job()
    elif jobtype == "Storage":
        assignedserveruuid = find_server_for_storage_job()

    #if masteruuid == "":
    #    masteruuid = get_uuid()
    if jobuuid == "":
        jobuuid = get_uuid()
    jobinputcursor = db.cursor()
    jobinputcursor.execute(
        "INSERT INTO Jobs(UUID, JobType, JobSubType, Command, CommandPreOptions, CommandOptions, JobInput, JobOutput, Assigned, State, AssignedServerUUID, StorageUUID, MasterUUID, Priority, Dependencies, Progress, AssignedTime, CreatedTime, ResultValue1, ResultValue2, JobOptions) VALUES('%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s')" %
        (jobuuid, jobtype, jobsubtype, command, commandpreoptions, commandoptions, input, output, 1, 0,
         assignedserveruuid, storageuuid,
         masteruuid, 1, dependencies, 0, timestamp, timestamp, "", "", joboptions))
    db.commit()
    db.close()
    return jobuuid