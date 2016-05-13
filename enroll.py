#!/usr/bin/env python

#
# Author: Vincenzo Maffione <v.maffione@nextworks.it>
#

import argparse
import socket
import time
import re

def printalo(byt):
    print(repr(byt).replace('\\n', '\n'))


description = "Python script to enroll IPCPs"
epilog = "2016 Vincenzo Maffione <v.maffione@nextworks.it>"

argparser = argparse.ArgumentParser(description = description,
                                    epilog = epilog)
argparser.add_argument('--ipcm-conf', help = "Path to the IPCM configuration file",
                       type = str, required = True)
argparser.add_argument('--enrollee-id', help = "ID of the enrolling IPCP",
                       type = int, required = True)
argparser.add_argument('--dif', help = "Name of DIF to enroll to",
                       type = str, required = True)
argparser.add_argument('--lower-dif', help = "Name of the lower level DIF",
                       type = int, required = True)
argparser.add_argument('--enroller-name', help = "Name of the remote neighbor IPCP to enroll to",
                       type = str, required = True)
args = argparser.parse_args()

HOST = '127.0.0.1'    # The remote host
PORT = 32766          # The same port as used by the server

socket_name = None

fin = open(args.ipcm_conf, 'r')
while 1:
    line = fin.readline()
    if line == '':
        break

    m = re.search(r'"(\S+ipcm-console.sock)', line)
    if m != None:
        socket_name = m.groups(1)
        break
fin.close()

if socket_name == None:
    print('Cannot find %s' % (socket_name))
    quit(1)

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

connected = False
trials = 0
while trials < 4:
    try:
        s.connect(socket_name)
        connected = True
        break
    except:
        pass
    trials += 1
    time.sleep(1)

if connected:
    try:
        data = s.recv(1024)
        printalo(data)

        cmd = 'enroll-to-dif %s %s %s %s 1\n' \
                % (args.enrollee_id, args.dif, args.lower_dif, args.enroller_name)

        s.sendall(bytes(cmd, 'ascii'))

        data = s.recv(1024)
        printalo(data)
    except:
        pass

else:
    print('Failed to connect to "%s"' % socket_name)

s.close()
