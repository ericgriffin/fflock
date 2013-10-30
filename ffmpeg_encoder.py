import subprocess
import re
import os
import time
import threading
import globals


class ffmpegencoder(threading.Thread):
    def __init__(self, inpath, outpath, codecSettings, encoder, overwrite, extraArgs=" "):
        """


        @rtype : none
        @param inpath:
        @param outpath:
        @param codecSettings:
        @param overwrite:
        @param extraArgs:
        """
        threading.Thread.__init__(self)
        self.encoder = encoder
        self.progress = 0
        # build args string
        strOverwrite = ["-n", "-y"][int(overwrite)]
        self.args = "%s %s -analyzeduration 1000000 -i %s %s %s %s" % (encoder,
            strOverwrite, inpath, codecSettings, extraArgs, outpath)
        print self.args


    def run(self):
        """



        @rtype : none
        """
        self.progress = 0
        self.startTime = self.getTime()

        #start subprocess object
        print "Encoding using", self.encoder
        proc = subprocess.Popen(self.args, shell=True, stderr=subprocess.PIPE)

        self.output = []        #all lines of output from FFMPEG
        self.durationFlt = -1    #duration of audio in seconds
        partialLine = ""        #currnt console line which is not complete

        # read a set amount of characters from ffmpeg's console output in order to build entire lines of output
        while True:
            #use smaller values for more updates per second
            data = proc.stderr.read(10)

            #break when there is no more data
            if len(data) == 0:
                break

            #data needs to be added to previous line
            if not "\r" in data:
                partialLine += data
            #lines are terminated in this string
            else:
                tmpLines = []

                #split by \r
                split = data.split("\r")

                #add the rest of partial line to first item of array
                if partialLine != "":
                    split[0] = partialLine + split[0]
                    partialLine = ""

                #add every item apart from last to tmpLines array
                if len(split) > 1:
                    for i in range(len(split) - 1):
                        tmpLines.append(split[i])

                #last item is '' if data string ends in \r
                #last line is partial, save for temporary storage
                if split[-1] != "":
                    partialLine = split[-1]
                #last line is terminated
                else:
                    tmpLines.append(split[-1])

                self.output.extend(tmpLines)

                #read each full line
                for fullLine in tmpLines:
                    #no duration yet
                    if self.durationFlt == -1:
                        #get duration via regex match
                        durPatern = re.compile("Duration: [0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]{2}")
                        durMatches = durPatern.findall(fullLine)
                        if self.durationFlt == -1 and len(durMatches) > 0:
                            #store duration as seconds
                            self.durationFlt = self.strToSecs(durMatches[0])

                    #duration found, get current time position of encode
                    else:
                        #get current time via regex match
                        timePattern = re.compile("time=[0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]{2}")
                        timeMatches = timePattern.findall(fullLine)
                        if self.durationFlt != -1 and len(timeMatches) > 0:
                            lastTimeMatch = self.strToSecs(timeMatches[0])
                            #store progress as a percentage
                            self.progress = 100 * (float(lastTimeMatch) / self.durationFlt)

        self.progress = 100

        #wait for process to end for return code
        self.returnCode = proc.wait()

    def getArgs(self):
        """



        @rtype : object
        @return:
        """
        return self.args


    def getInputDuration(self):
        """


        @return: @raise Exception:
        """
        if self.durationFlt != -1:
            return self.durationFlt
        else:
            return self.durationFlt
            #raise Exception("Cannot obtain duration before encode start")


    def getProgress(self):

        """


        @return:
        """
        return self.progress


    def getEta(self):
        """


        @return:
        """
        if self.progress > 5:
            return (self.getElapsedTime() / self.progress) * (100 - self.progress)
        else:
            return -1


    def getReturnCode(self):
        """


        @return: @raise Exception:
        """
        try:
            return self.returnCode
        except:
            raise Exception("Cannot get return code before program end")


    def getLastOutput(self):
        """


        @return:
        """
        return (self.output[-1] if len(self.output) > 0 else None)


    def getElapsedTime(self):
        """


        @return: @raise Exception:
        """
        try:
            return self.getTime() - self.startTime
        except:
            raise Exception("Cannot get elapsed encode time before encode start")


    def strToSecs(self, input):
        """

        @param input:
        @return:
        """
        text = re.compile("[0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]{2}").findall(input)[-1]
        blocks = re.compile("[0-9]{2}").findall(text)
        h = int(blocks[0])
        m = int(blocks[1])
        s = int(blocks[2])
        ms = int(blocks[3])
        return h * 60 * 60 + m * 60 + s + ms * 0.1


    def getTime(self):
        """


        @return:
        """
        return (time.clock() if os.name == 'nt' else time.time())
