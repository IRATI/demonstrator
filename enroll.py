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


def get_response(s):
    data = bytes()
    while 1:
        data += s.recv(1024)
        lines = str(data).replace('\\n', '\n').split('\n')
        #print(lines)
        if lines[-1].find("IPCM") != -1:
            return lines[:len(lines)-1]


description = "Python script to enroll IPCPs"
epilog = "2016 Vincenzo Maffione <v.maffione@nextworks.it>"

argparser = argparse.ArgumentParser(description = description,
                                    epilog = epilog)
argparser.add_argument('--ipcm-conf', help = "Path to the IPCM configuration file",
                       type = str, required = True)
argparser.add_argument('--enrollee-name', help = "Name of the enrolling IPCP",
                       type = str, required = True)
argparser.add_argument('--dif', help = "Name of DIF to enroll to",
                       type = str, required = True)
argparser.add_argument('--lower-dif', help = "Name of the lower level DIF",
                       type = str, required = True)
argparser.add_argument('--enroller-name', help = "Name of the remote neighbor IPCP to enroll to",
                       type = str, required = True)
args = argparser.parse_args()

socket_name = None

fin = open(args.ipcm_conf, 'r')
while 1:
    line = fin.readline()
    if line == '':
        break

    m = re.search(r'"(\S+ipcm-console.sock)', line)
    if m != None:
        socket_name = m.group(1)
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
        # Receive the banner
        get_response(s)

        # Send the IPCP list command
        cmd = 'list-ipcps\n'
        s.sendall(bytes(cmd, 'ascii'))

        # Get the list of IPCPs and parse it to look for the enroller ID
        print('Looking up identifier for IPCP %s' % args.enrollee_name)
        lines = get_response(s)
        print(lines)
        enrollee_id = None
        for line in lines:
            rs = r'^\s*(\d+)\s*\|\s*' + args.enrollee_name.replace('.', '\\.')
            m = re.match(rs, line)
            if m != None:
                enrollee_id = m.group(1)

        if enrollee_id == None:
            print('Could not find the ID of enrollee IPCP %s' \
                    % args.enrollee_name)
            raise Exception()

        # Send the enroll command
        cmd = 'enroll-to-dif %s %s %s %s 1\n' \
                % (enrollee_id, args.dif, args.lower_dif, args.enroller_name)
        print(cmd)

        s.sendall(bytes(cmd, 'ascii'))

        # Get the enroll command answer
        lines = get_response(s)
        print(lines)
    except:
        s.close()
        raise

else:
    print('Failed to connect to "%s"' % socket_name)

s.close()
