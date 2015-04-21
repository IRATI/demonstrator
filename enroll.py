#!/usr/bin/env python

# Echo client program
import socket
import sys

def printalo(byt):
    print(repr(byt).replace('\\n', '\n'))


vlan = sys.argv[1]
pvid = sys.argv[2]

HOST = '127.0.0.1'    # The remote host
PORT = 32766              # The same port as used by the server
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))

data = s.recv(1024)
printalo(data)

s.sendall(bytes('enroll-to-dif 4 n.DIF %s n.%s.IPCP 1\n' % (vlan, pvid), 'ascii'))

data = s.recv(1024)
printalo(data)

s.close()
