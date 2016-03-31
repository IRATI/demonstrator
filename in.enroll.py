#!/usr/bin/env python

#
# Author: Vincenzo Maffione <v.maffione@nextworks.it>
#

import socket
import sys
import time

def printalo(byt):
    print(repr(byt).replace('\\n', '\n'))


vlan = sys.argv[1]
pvid = sys.argv[2]

HOST = '127.0.0.1'    # The remote host
PORT = 32766              # The same port as used by the server

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

trials = 0
while trials < 4:
    try:
        s.connect("INSTALLPATH/var/ipcm-console.sock")
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
