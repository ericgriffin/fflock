#!/usr/bin/python

import sys
import os
import socket
import urllib2
import uuid
import re
import glob
import MySQLdb
import subprocess
from subprocess import PIPE, Popen
from re import search
from datetime import datetime
from xml.dom import minidom
import boto
import boto.s3.connection
import fflock_globals


socket.setdefaulttimeout(12)


def dbconnect():
    """


    @rtype : db pointer
    @return:
    """
    try:
        db = MySQLdb.connect(host=fflock_globals.DATABASE_HOST, user=fflock_globals.DATABASE_USER, passwd=fflock_globals.DATABASE_PASSWD,
                             port=int(fflock_globals.DATABASE_PORT), db=fflock_globals.DATABASE_NAME)
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


def ensure_dir(path, storageuuid):
    if not path.startswith("http://") and not path.startswith("https://") and not path.startswith(
            "ftp://") and not path.startswith("s3://"):

        d = os.path.dirname(path)
        if not os.path.exists(d):
            print "CREATING OUTPUT FOLDER"
            d_fullpath = get_storage_nfs_folder_path(storageuuid[0]) + d
            os.makedirs(d_fullpath)


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


def job_cleanup(jobuuid, storageuuid, masteruuid, jobinput, joboutput):
    """


    @rtype : Boolean
    @return:
    """


    print "jobinput:", jobinput
    print "joboutput:", joboutput
    db = dbconnect()
    jobcursor = db.cursor()

    # delete externally downloaded sources
    if jobinput.startswith("http://") or jobinput.startswith("https://") or jobinput.startswith(
            "ftp://") or jobinput.startswith("s3://"):
        nfsmountpath = get_storage_nfs_folder_path(storageuuid)
        externalinputfile = nfsmountpath + jobinput.split('/')[-1]
        print "Deleting downloaded source file ", externalinputfile
        os.remove(externalinputfile)

    # delete intermediate files
    if joboutput.startswith("http://") or joboutput.startswith("https://") or joboutput.startswith(
            "ftp://") or joboutput.startswith("s3://"):
        joboutput = joboutput.split('/')[-1]

    todelete = get_storage_nfs_folder_path(storageuuid) + joboutput + "_*"
    print "INTERMEDIATE FILES: ", todelete
    for file in glob.glob(todelete):
        print "delete ", file
        os.remove(file)

    # delete the master job
    deletecursor = db.cursor()
    deletecursor.execute("DELETE FROM Jobs WHERE UUID='%s'" % masteruuid)

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
            "SELECT JobType, Assigned, State, AssignedServerUUID, Priority, Dependencies, Progress FROM Jobs WHERE AssignedServerUUID = '%s'" % str(
                storageserveruuid))
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
    print "Fetching", url, "to", filename
    header = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
        'Accept-Encoding': 'none',
        'Accept-Language': 'en-US,en;q=0.8',
        'Connection': 'keep-alive'}

    count = 1
    file_fetched = 0

    while count <= fflock_globals.FETCH_RETRIES:
        try:
            req = urllib2.Request(url, headers=header)
            u = urllib2.urlopen(req)
        except urllib2.URLError:
            print "*** Error - Failed to fetch file", url
            count += 1
        else:
            count = fflock_globals.FETCH_RETRIES + 1
            file_fetched = 1

    if file_fetched == 0:
        return False

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
    print "Fetching", url, "to", filename
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
    print "Fetching file", filename, "from AWS S3 bucket", fflock_globals.S3BUCKET
    conn = boto.connect_s3(str(fflock_globals.S3ID), str(fflock_globals.S3KEY))
    bucket = conn.get_bucket(str(fflock_globals.S3BUCKET))
    key = bucket.get_key(file_name)
    key.get_contents_to_filename(filename)
    return True


def upload_file_s3(source, destination):
    destination_path = destination.split('//')[-1]
    destination_path = "/" + destination_path
    file_name = source.split('//')[-1]
    conn = boto.connect_s3(str(fflock_globals.S3ID), str(fflock_globals.S3KEY))
    bucket = conn.get_bucket(str(fflock_globals.S3BUCKET))
    key = bucket.new_key(destination_path)
    print "Pushing file", source, "to AWS S3 bucket", fflock_globals.S3BUCKET, "as", destination_path
    key.set_contents_from_filename(file_name)
    os.remove(source)
    return True


def parse_config_file(configfile, type):
    """


    @rtype : none
    """
    xmldoc = minidom.parse(configfile)
    if type == "slave":
        config = xmldoc.getElementsByTagName('slaveconfig')
        for s in config:
            fflock_globals.DATABASE_HOST = s.attributes['dbhost'].value
            fflock_globals.DATABASE_PORT = s.attributes['dbport'].value
            fflock_globals.DATABASE_USER = s.attributes['dbuser'].value
            fflock_globals.DATABASE_PASSWD = s.attributes['dbpasswd'].value
            fflock_globals.DATABASE_NAME = s.attributes['dbname'].value
            fflock_globals.ENCODER = s.attributes['encoder'].value
            fflock_globals.SLAVE_MOUNT_PREFIX_PATH = s.attributes['slavemountprefix'].value
    elif type == "storage":
        config = xmldoc.getElementsByTagName('storageconfig')
        for s in config:
            fflock_globals.DATABASE_HOST = s.attributes['dbhost'].value
            fflock_globals.DATABASE_PORT = s.attributes['dbport'].value
            fflock_globals.DATABASE_USER = s.attributes['dbuser'].value
            fflock_globals.DATABASE_PASSWD = s.attributes['dbpasswd'].value
            fflock_globals.DATABASE_NAME = s.attributes['dbname'].value
            fflock_globals.ENCODER = s.attributes['encoder'].value
            fflock_globals.NFS_PATH = s.attributes['nfspath'].value
            fflock_globals.S3ID = s.attributes['s3id'].value
            fflock_globals.S3KEY = s.attributes['s3key'].value
            fflock_globals.S3BUCKET = s.attributes['s3bucket'].value
    elif type == "master":
        config = xmldoc.getElementsByTagName('masterconfig')
        for s in config:
            fflock_globals.DATABASE_HOST = s.attributes['dbhost'].value
            fflock_globals.DATABASE_PORT = s.attributes['dbport'].value
            fflock_globals.DATABASE_USER = s.attributes['dbuser'].value
            fflock_globals.DATABASE_PASSWD = s.attributes['dbpasswd'].value
            fflock_globals.DATABASE_NAME = s.attributes['dbname'].value
            fflock_globals.ENCODER = s.attributes['encoder'].value
    elif type == "admin":
        config = xmldoc.getElementsByTagName('adminconfig')
        for s in config:
            fflock_globals.DATABASE_HOST = s.attributes['dbhost'].value
            fflock_globals.DATABASE_PORT = s.attributes['dbport'].value
            fflock_globals.DATABASE_USER = s.attributes['dbuser'].value
            fflock_globals.DATABASE_PASSWD = s.attributes['dbpasswd'].value
            fflock_globals.DATABASE_NAME = s.attributes['dbname'].value


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