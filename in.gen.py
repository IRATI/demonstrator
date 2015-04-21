#!/usr/bin/env python

import re
import subprocess


install_path = "INSTALLPATH"
vm_img_path = "VMIMGPATH"

fin = open('gen.conf', 'r')

vms = dict()
bridges = dict()
links = []

while 1:
    line = fin.readline()
    if line == '':
        break

    line = line.replace('\n', '')

    m = re.match(r'\s*vm\s+(\w+)', line)
    if m:
        name = m.group(1)
        vms[name] = {'name': name, 'ports': []}
        continue

    m = re.match(r'\s*bridge\s+(\w+)\s+(\d+)', line)
    if m:
        name = m.group(1)
        vlan = m.group(2)
        bridges[name] = {'name': name, 'vlan': vlan}
        continue

    m = re.match(r'\s*link\s+(\w+)\s+(\w+)', line)
    if m:
        bridge = m.group(1)
        vm = m.group(2)
        links.append((bridge, vm))
        continue

fin.close()


# up script
fout = open('up.sh', 'w')

outs =  '#!/bin/bash\n'             \
        '\n'                        \
        'set -x\n'                  \
        '\n';

for b in bridges:
    outs += 'sudo brctl addbr %(br)s\n'         \
            'sudo ip link set %(br)s up\n'      \
            '\n' % {'br': b}

for l in links:
    b, vm = l
    vlan = bridges[b]['vlan']
    idx = len(vms[vm]['ports']) + 1
    tap = '%s.%02x' % (vm, idx)

    outs += 'sudo ip tuntap add mode tap name %(tap)s\n'    \
            'sudo ip link set %(tap)s up\n'                 \
            'sudo brctl addif %(br)s %(tap)s\n\n'           \
                % {'tap': tap, 'br': b}

    vms[vm]['ports'].append({'tap': tap, 'br': b, 'idx': idx,
                             'vlan': vlan})


vmid = 1

for i in vms:
    vm = vms[i]

    vm['id'] = vmid

    fwdp = 2222 + vmid
    mac = '00:0a:0a:0a:%02x:%02x' % (vmid, 99)

    vm['ssh'] = fwdp

    outs += ''                                                  \
            'qemu-system-x86_64 "%(vmimage)s" '   \
            '-snapshot '                                                \
            '--enable-kvm '                                             \
            '-smp 2 '                                                   \
            '-m 256M '                                                  \
            '-device e1000,mac=%(mac)s,netdev=mgmt '                    \
            '-netdev user,id=mgmt,hostfwd=tcp::%(fwdp)s-:22 '           \
            '-vga std '                                                 \
            '-pidfile rina-%(id)s.pid '                                 \
            '-display none ' % {'fwdp': fwdp, 'id': vmid, 'mac': mac,
                                'vmimage': vm_img_path}

    for port in vm['ports']:
        tap = port['tap']
        mac = '00:0a:0a:0a:%02x:%02x' % (vmid, port['idx'])
        port['mac'] = mac

        outs += ''                                                      \
        '-device e1000,mac=%(mac)s,netdev=data%(idx)s '                 \
        '-netdev tap,ifname=%(tap)s,id=data%(idx)s,script=no,downscript=no '\
            % {'mac': mac, 'tap': tap, 'idx': port['idx']}

    outs += '&\n\n'

    vmid += 1

for i in vms:
    vm = vms[i]

    outs += ''\
            'DONE=255\n'\
            'while [ $DONE != "0" ]; do\n'\
            '   ssh -p %(ssh)s localhost << \'ENDSSH\'\n'\
            'set -x\n'\
            'sudo hostname %(name)s\n'\
            '\n'\
            'sudo sed -i "s|vmid|%(id)s|g" /etc/template.conf\n'\
            '\n' % {'name': vm['name'], 'ssh': vm['ssh'], 'id': vm['id']}

    for port in vm['ports']:
        outs += 'PORT=$(mac2ifname %(mac)s)\n'\
                'sudo ip link set $PORT up\n'\
                'sudo ip link add link $PORT name $PORT.%(vlan)s type vlan id %(vlan)s\n'\
                'sudo ip link set $PORT.%(vlan)s up\n'\
                'sudo sed -i "s|ifc%(idx)s|$PORT|g" /etc/template.conf\n'\
                'sudo sed -i "s|vlan%(idx)s|%(vlan)s|g" /etc/template.conf\n'\
                    % {'mac': port['mac'], 'idx': port['idx'],
                       'id': vm['id'], 'vlan': port['vlan']}

    outs +=     'sudo modprobe shim-eth-vlan\n'\
                'sudo modprobe normal-ipcp\n'\
                'sudo modprobe rina-default-plugin\n'\
                'sudo %(installpath)s/bin/ipcm -c /etc/template.conf -l DBG &> log &\n'\
                '\n'\
                'true\n'\
            'ENDSSH\n'\
            '   DONE=$?\n'\
            '   if [ $DONE != "0" ]; then\n'\
            '       sleep 1\n'\
            '   fi\n'\
            'done\n\n' % {'installpath': install_path}


for br in bridges:
    br_vms = []
    for l in links:
        b, vm = l
        if b == br:
            br_vms.append(vm)

    if len(br_vms) < 2:
        continue

    pvm_name = br_vms[0]

    outs += 'sleep 5\n' # important!!

    for vm_name in br_vms:
        if vm_name == pvm_name:
            continue

        vm = vms[vm_name]

        outs += ''\
            'DONE=255\n'\
            'while [ $DONE != "0" ]; do\n'\
            '   ssh -p %(ssh)s localhost << \'ENDSSH\'\n'\
            'enroll.py %(vlan)s %(pvid)s\n'\
            'true\n'\
            'ENDSSH\n'\
            '   DONE=$?\n'\
            '   if [ $DONE != "0" ]; then\n'\
            '       sleep 1\n'\
            '   fi\n'\
            'done\n\n' % {'ssh': vm['ssh'], 'id': vm['id'],
                          'pvid': vms[pvm_name]['id'],
                          'vlan': bridges[br]['vlan']}

    print("bridge %s vms %s"% (br, br_vms))

fout.write(outs)

fout.close()

subprocess.call(['chmod', '+x', 'up.sh'])


# down script
fout = open('down.sh', 'w')

outs =  '#!/bin/bash\n'             \
        '\n'                        \
        'set -x\n'                  \
        '\n'                        \
        'kill_qemu() {\n'           \
        '   PIDFILE=$1\n'           \
        '   PID=$(cat $PIDFILE)\n'  \
        '   if [ -n $PID ]; then\n' \
        '       kill $PID\n'        \
        '       while [ -n "$(ps -p $PID -o comm=)" ]; do\n'    \
        '           sleep 1\n'                                  \
        '       done\n'                                         \
        '   fi\n'                                               \
        '\n'                                                    \
        '   rm $PIDFILE\n'                                      \
        '}\n\n'

for i in vms:
    vm = vms[i]
    outs += 'kill_qemu rina-%(id)s.pid\n' % {'id': vm['id']}

outs += '\n'

for i in vms:
    vm = vms[i]
    for port in vm['ports']:
        tap = port['tap']
        b = port['br']

        outs += 'sudo brctl delif %(br)s %(tap)s\n'             \
                'sudo ip link set %(tap)s down\n'               \
                'sudo ip tuntap del mode tap name %(tap)s\n\n'  \
                    % {'tap': tap, 'br': b}

for b in bridges:
    outs += 'sudo ip link set %(br)s down\n'        \
            'sudo brctl delbr %(br)s\n'             \
            '\n' % {'br': b}

fout.write(outs)

fout.close()

subprocess.call(['chmod', '+x', 'down.sh'])
