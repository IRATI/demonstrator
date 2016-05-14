#!/usr/bin/env python

#
# Author: Vincenzo Maffione <v.maffione@nextworks.it>
#

import gen_templates
import subprocess
import json
import copy
import re
import os


######################## Compile mac2ifname program ########################
try:
    subprocess.call(['cc', '-Wall', '-o', 'mac2ifname', 'mac2ifname.c'])
except:
    print('Cannot find a C compiler to compile mac2ifname program')
    quit(1)

env_dict = {}
keywords = ['vmimgpath', 'installpath', 'username', 'baseport']


############################## Parse gen.env ###############################
fin = open('gen.env', 'r')
while 1:
    line = fin.readline()
    if line == '':
        break

    m = re.match(r'(\S+)\s*=\s*(\S+)', line)
    if m == None:
        continue

    key = m.group(1)
    value = m.group(2)

    if key not in keywords:
        print('Unrecognized keyword %s' % (key))
        continue

    env_dict[key] = value
fin.close()

for key in keywords:
    if key not in env_dict:
        print("Configuration variables missing")
        quit(1)

env_dict['baseport'] = int(env_dict['baseport'])


############################# Parse gen.conf ##############################
fin = open('gen.conf', 'r')

vms = dict()
bridges = dict()
links = []
difs = dict()
enrollments = dict()

linecnt = 0

while 1:
    line = fin.readline()
    if line == '':
        break
    linecnt += 1

    line = line.replace('\n', '')

    if line.startswith('#'):
        continue

    m = re.match(r'\s*eth\s+(\w+)\s+(\d+)\s+(\w.*)$', line)
    if m:
        bridge = m.group(1)
        vlan = m.group(2)
        vm_list = m.group(3).split()

        if bridge in bridges:
            print('Error: Line %d: bridge %s already defined' \
                                            % (linecnt, bridge))
            continue

        bridges[bridge] = {'name': bridge, 'vlan': vlan}

        for vm in vm_list:
            if vm not in vms:
                vms[vm] = {'name': vm, 'ports': []}
            links.append((bridge, vm))

        #for i in range(len(vm_list)-1):
        #    for j in range(i + 1, len(vm_list)):
        #        print(vm_list[i], vm_list[j])
        continue

    m = re.match(r'\s*dif\s+(\w+)\s+(\w+)\s+(\w.*)$', line)
    if m:
        dif = m.group(1)
        vm = m.group(2)
        dif_list = m.group(3).split()

        if vm not in vms:
            vms[vm] = {'name': vm, 'ports': []}

        if dif not in difs:
            difs[dif] = dict()

        if vm in difs[dif]:
            print('Error: Line %d: vm %s in dif %s already specified' \
                                            % (linecnt, vm, dif))
            continue

        difs[dif][vm] = dif_list

        continue

fin.close()


####################### Compute DIF graphs #######################
for dif in difs:
    neighsets = dict()
    graph = dict()
    first = None

    # For each N-1-DIF supporting this DIF, compute the set of nodes that
    # share such N-1-DIF. This set will be called the 'neighset' of
    # the N-1-DIF for the current DIF.

    for vmname in difs[dif]:
        graph[vmname] = [] # init for later use
        if first == None: # pick any node for later use
            first = vmname
        first = vmname
        for lower_dif in difs[dif][vmname]:
            if lower_dif not in neighsets:
                neighsets[lower_dif] = []
            neighsets[lower_dif].append(vmname)

    # Build the graph, represented as adjacency list
    for lower_dif in neighsets:
        # Each neighset corresponds to a complete (sub)graph.
        for vm1 in neighsets[lower_dif]:
            for vm2 in neighsets[lower_dif]:
                if vm1 != vm2:
                    graph[vm1].append((vm2, lower_dif))

    # To generate the list of enrollments, we simulate one,
    # using breadth-first trasversal.
    enrolled = set([first])
    frontier = set([first])
    enrollments[dif] = []
    while len(frontier):
        cur = frontier.pop()
        for edge in graph[cur]:
            if edge[0] not in enrolled:
                enrolled.add(edge[0])
                enrollments[dif].append({'enrollee': edge[0],
                                         'enroller': cur,
                                         'lower_dif': edge[1]})
                frontier.add(edge[0])

    #print(neighsets)
    #print(graph)

print(enrollments)

###################### Generate UP script ########################
fout = open('up.sh', 'w')

outs =  '#!/bin/bash\n'             \
        '\n'                        \
        'set -x\n'                  \
        '\n';

for b in sorted(bridges):
    outs += 'sudo brctl addbr %(br)s\n'         \
            'sudo ip link set %(br)s up\n'      \
            '\n' % {'br': b}

for l in sorted(links):
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

for vmname in sorted(vms):
    vm = vms[vmname]

    vm['id'] = vmid

    fwdp = env_dict['baseport'] + vmid
    fwdc = fwdp + 10000
    mac = '00:0a:0a:0a:%02x:%02x' % (vmid, 99)

    vm['ssh'] = fwdp

    outs += ''                                                  \
            'qemu-system-x86_64 "%(vmimage)s" '   \
            '-snapshot '                                                \
            '--enable-kvm '                                             \
            '-smp 2 '                                                   \
            '-m 128M '                                                  \
            '-device e1000,mac=%(mac)s,netdev=mgmt '                    \
            '-netdev user,id=mgmt,hostfwd=tcp::%(fwdp)s-:22 '           \
            '-serial tcp:127.0.0.1:%(fwdc)s,server,nowait '             \
            '-vga std '                                                 \
            '-pidfile rina-%(id)s.pid '                                 \
            '-display none ' % {'fwdp': fwdp, 'id': vmid, 'mac': mac,
                                'vmimage': env_dict['vmimgpath'], 'fwdc': fwdc}

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

for vmname in sorted(vms):
    vm = vms[vmname]

    gen_files_conf = 'shimeth.%(name)s.*.dif normal.*.dif %(name)s.ipcm.conf ' \
                        % {'name': vm['name']}
    gen_files_bin = 'enroll.py mac2ifname '
    gen_files = gen_files_conf + gen_files_bin

    outs += ''\
            'DONE=255\n'\
            'while [ $DONE != "0" ]; do\n'\
            '   scp -P %(ssh)s %(genfiles)s %(username)s@localhost: \n'\
            '   DONE=$?\n'\
            '   if [ $DONE != "0" ]; then\n'\
            '       sleep 1\n'\
            '   fi\n'\
            'done\n\n'\
            'ssh -p %(ssh)s %(username)s@localhost << \'ENDSSH\'\n'\
                'set -x\n'\
                'sudo hostname %(name)s\n'\
                '\n'\
                'sudo mv %(genfilesconf)s /etc\n'\
                'sudo mv %(genfilesbin)s /usr/bin\n'\
            '\n' % {'name': vm['name'], 'ssh': vm['ssh'], 'id': vm['id'],
                    'username': env_dict['username'],
                    'genfiles': gen_files, 'genfilesconf': gen_files_conf,
                    'genfilesbin': gen_files_bin, 'vmname': vm['name']}

    for port in vm['ports']:
        outs += 'PORT=$(mac2ifname %(mac)s)\n'\
                'sudo ip link set $PORT up\n'\
                'sudo ip link add link $PORT name $PORT.%(vlan)s type vlan id %(vlan)s\n'\
                'sudo ip link set $PORT.%(vlan)s up\n'\
                'sudo sed -i "s|ifc%(idx)s|$PORT|g" /etc/shimeth.%(vmname)s.%(vlan)s.dif\n'\
                    % {'mac': port['mac'], 'idx': port['idx'],
                       'id': vm['id'], 'vlan': port['vlan'],
                       'vmname': vm['name']}

    outs +=     'sudo modprobe shim-eth-vlan\n'\
                'sudo modprobe normal-ipcp\n'\
                'sudo modprobe rina-default-plugin\n'\
                'sudo %(installpath)s/bin/ipcm -a "scripting, console, mad" '\
                            '-c /etc/%(vmname)s.ipcm.conf -l DEBUG &> log &\n'\
                'sleep 1\n'\
                'true\n'\
            'ENDSSH\n' % {'installpath': env_dict['installpath'],
                          'vmname': vm['name']}


for br in sorted(bridges):
    br_vms = []
    for l in links:
        b, vm = l
        if b == br:
            br_vms.append(vm)

    if len(br_vms) < 2:
        continue

    pvm_name = br_vms[0]

    outs += 'sleep 2\n' # important!!

    for vm_name in sorted(br_vms):
        if vm_name == pvm_name:
            continue

        vm = vms[vm_name]

        outs += ''\
            'DONE=255\n'\
            'while [ $DONE != "0" ]; do\n'\
            '   ssh -p %(ssh)s %(username)s@localhost << \'ENDSSH\'\n'\
            'set -x\n'\
            'sudo enroll.py --lower-dif %(vlan)s --dif n1.DIF '\
                        '--ipcm-conf /etc/%(vmname)s.ipcm.conf '\
                        '--enrollee-id %(eid)s '\
                        '--enroller-name n1.%(pvid)s.IPCP\n'\
            'sleep 1\n'\
            'true\n'\
            'ENDSSH\n'\
            '   DONE=$?\n'\
            '   if [ $DONE != "0" ]; then\n'\
            '       sleep 1\n'\
            '   fi\n'\
            'done\n\n' % {'ssh': vm['ssh'], 'id': vm['id'],
                          'pvid': vms[pvm_name]['id'],
                          'vlan': bridges[br]['vlan'],
                          'username': env_dict['username'],
                          'vmname': vm['name'],
                          'eid': len(vm['ports']) + 1}

    print("bridge %s vms %s"% (br, br_vms))

fout.write(outs)

fout.close()

subprocess.call(['chmod', '+x', 'up.sh'])


###################### Generate DOWN script ########################
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

for vmname in sorted(vms):
    vm = vms[vmname]
    outs += 'kill_qemu rina-%(id)s.pid\n' % {'id': vm['id']}

outs += '\n'

for vmname in sorted(vms):
    vm = vms[vmname]
    for port in vm['ports']:
        tap = port['tap']
        b = port['br']

        outs += 'sudo brctl delif %(br)s %(tap)s\n'             \
                'sudo ip link set %(tap)s down\n'               \
                'sudo ip tuntap del mode tap name %(tap)s\n\n'  \
                    % {'tap': tap, 'br': b}

for b in sorted(bridges):
    outs += 'sudo ip link set %(br)s down\n'        \
            'sudo brctl delbr %(br)s\n'             \
            '\n' % {'br': b}

fout.write(outs)

fout.close()

subprocess.call(['chmod', '+x', 'down.sh'])


################## Generate IPCM/DIF configuration files ##################
ipcmconfs = dict()
for vmname in sorted(vms):
    ipcmconfs[vmname] = copy.deepcopy(gen_templates.ipcmconf_base)

difconfs = dict()
for dif in sorted(difs):
    difconfs[dif] = copy.deepcopy(gen_templates.normal_dif_base)

for vmname in sorted(vms):
    vm = vms[vmname]
    ipcmconf = ipcmconfs[vmname]

    for port in vm['ports']:
        ipcmconf["ipcProcessesToCreate"].append({
                                "apName": "eth.%d.IPCP" % port['idx'],
                                "apInstance": "1",
                                "difName": port['vlan']
                                })

        template_file_name = 'shimeth.%s.%s.dif' % (vm['name'], port['vlan'])
        ipcmconf["difConfigurations"].append({
                                "name": port['vlan'],
                                "template": template_file_name
                                })

        fout = open(template_file_name, 'w')
        fout.write(json.dumps({"difType": "shim-eth-vlan",
                               "configParameters": {
                                    "interface-name": "ifc%d" % (port['idx'],)
                                    }
                              },
                              indent=4, sort_keys=True))
        fout.close()


for dif in sorted(difs):
    difconf = difconfs[dif]

    for vmname in sorted(difs[dif]):
        vm = vms[vmname]
        ipcmconf = ipcmconfs[vmname]

        normal_ipcp = { "apName": "%s.%d.IPCP" % (dif, vm['id']),
                        "apInstance": "1",
                        "difName": "%s.DIF" % (dif,) }

        normal_ipcp["difsToRegisterAt"] = []
        for port in vm['ports']:
            normal_ipcp["difsToRegisterAt"].append(port['vlan'])
        ipcmconf["ipcProcessesToCreate"].append(normal_ipcp)

        ipcmconf["difConfigurations"].append({
                                "name": "%s.DIF" % (dif,),
                                "template": "normal.%s.dif" % (dif,)
                                })

        difconf["knownIPCProcessAddresses"].append({
                                    "apName":  "%s.%d.IPCP" % (dif, vm['id']),
                                    "apInstance": "1",
                                    "address": 16 + vm['id']
                                })


for vmname in sorted(vms):
    # Dump the IPCM configuration files
    ipcmconf_str = json.dumps(ipcmconfs[vmname], indent = 4,
                              sort_keys = True) % env_dict
    fout = open('%s.ipcm.conf' % (vmname,), 'w')
    fout.write(ipcmconf_str);
    fout.close()

for dif in sorted(difs):
    # Dump the normal DIF configuration files
    difconf_str = json.dumps(difconf, indent = 4, sort_keys = True) % env_dict
    fout = open('normal.%s.dif' % (dif,), 'w')
    fout.write(difconf_str);
    fout.close()

