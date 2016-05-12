#!/usr/bin/env python

#
# Author: Vincenzo Maffione <v.maffione@nextworks.it>
#

import socket
import sys
import time
import re

def printalo(byt):
    print(repr(byt).replace('\\n', '\n'))


vlan = sys.argv[1]
pvid = sys.argv[2]

HOST = '127.0.0.1'    # The remote host
PORT = 32766          # The same port as used by the server

socket_name = None

fin = open('/etc/template.conf', 'r')
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

trials = 0
while trials < 4:
    try:
        s.connect(socket_name)
        break
    except:
        pass
    trials += 1
    time.sleep(1)

try:
    data = s.recv(1024)
    printalo(data)

    s.sendall(bytes('enroll-to-dif 4 n.DIF %s n.%s.IPCP 1\n' % (vlan, pvid), 'ascii'))

    data = s.recv(1024)
    printalo(data)
except:
    pass

s.close()
