#!/usr/bin/env python

#
# Author: Vincenzo Maffione <v.maffione@nextworks.it>
#

import gen_templates
import subprocess
import argparse
import json
import copy
import re
import os


def which(program):
    retcode = subprocess.call(['which', program], stderr = subprocess.DEVNULL,
                              stdout = subprocess.DEVNULL)
    if retcode != 0:
        print('Fatal error: Cannot find "%s" program' % program)
        quit(1)


description = "Python script to generate IRATI deployments for Virtual Machines"
epilog = "2016 Vincenzo Maffione <v.maffione@nextworks.it>"

argparser = argparse.ArgumentParser(description = description,
                                    epilog = epilog)
argparser.add_argument('-c', '--conf',
                       help = "gen.conf configuration file", type = str,
                       default = 'gen.conf')
args = argparser.parse_args()


which('brctl')
which('qemu-system-x86_64')


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
fin = open(args.conf, 'r')

vms = dict()
shims = dict()
links = []
difs = dict()
enrollments = dict()
dif_policies = dict()

linecnt = 0

while 1:
    line = fin.readline()
    if line == '':
        break
    linecnt += 1

    line = line.replace('\n', '')

    if line.startswith('#'):
        continue

    m = re.match(r'\s*eth\s+(\d+)\s+(\w.*)$', line)
    if m:
        vlan = m.group(1)
        vm_list = m.group(2).split()

        if vlan in shims:
            print('Error: Line %d: shim %s already defined' \
                                            % (linecnt, vlan))
            continue

        shims[vlan] = {'bridge': 'rbr' + vlan, 'vlan': vlan}

        for vm in vm_list:
            if vm not in vms:
                vms[vm] = {'name': vm, 'ports': []}
            links.append((vlan, vm))

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

    m = re.match(r'\s*policy\s+(\w+)\s+([\w.-]+)\s+([\w-]+)', line)
    if m:
        dif = m.group(1)
        path = m.group(2)
        ps = m.group(3)

        if dif not in dif_policies:
            dif_policies[dif] = []

        dif_policies[dif].append({'path': path, 'ps': ps})
        if path not in gen_templates.policy_translator:
            print('Unknown component path "%s"' % path)
            quit(1)

        continue

fin.close()

for dif in difs:
    if dif not in dif_policies:
        dif_policies[dif] = []

################ Compute enrollment order for DIFs ##################

# Compute DIFs dependency graph, as both adjacency and incidence list.
difsdeps_adj = dict()
difsdeps_inc = dict()
for dif in difs:
    difsdeps_inc[dif] = set()
    difsdeps_adj[dif] = set()
for shim in shims:
    difsdeps_inc[shim] = set()
    difsdeps_adj[shim] = set()

for dif in difs:
    for vmname in difs[dif]:
        for lower_dif in difs[dif][vmname]:
            difsdeps_inc[dif].add(lower_dif)
            difsdeps_adj[lower_dif].add(dif)

# Kahn's algorithm below only needs per-node count of
# incident edges, so we compute these counts from the
# incidence list and drop the latter.
difsdeps_inc_cnt = dict()
for dif in difsdeps_inc:
    difsdeps_inc_cnt[dif] = len(difsdeps_inc[dif])
del difsdeps_inc

#print(difsdeps_adj)
#print(difsdeps_inc_inc)

# Run Kahn's algorithm to compute topological ordering on the DIFs graph.
frontier = set()
dif_ordering = []
for dif in difsdeps_inc_cnt:
    if difsdeps_inc_cnt[dif] == 0:
        frontier.add(dif)

while len(frontier):
    cur = frontier.pop()
    dif_ordering.append(cur)
    for nxt in difsdeps_adj[cur]:
        difsdeps_inc_cnt[nxt] -= 1
        if difsdeps_inc_cnt[nxt] == 0:
            frontier.add(nxt)
    difsdeps_adj[cur] = set()

circular_set = [dif for dif in difsdeps_inc_cnt if difsdeps_inc_cnt[dif] != 0]
if len(circular_set):
    print("Fatal error: The specified DIFs topology has one or more"\
          "circular dependencies, involving the following"\
          " DIFs: %s" % circular_set)
    print("             DIFs dependency graph: %s" % difsdeps_adj);
    quit(1)


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

for shim in shims:
    enrollments[shim] = dict()


###################### Generate UP script ########################
fout = open('up.sh', 'w')

outs =  '#!/bin/bash\n'             \
        '\n'                        \
        'set -x\n'                  \
        '\n';

for shim in sorted(shims):
    outs += 'sudo brctl addbr %(br)s\n'         \
            'sudo ip link set %(br)s up\n'      \
            '\n' % {'br': shims[shim]['bridge']}

for l in sorted(links):
    shim, vm = l
    b = shims[shim]['bridge']
    idx = len(vms[vm]['ports']) + 1
    tap = '%s.%02x' % (vm, idx)

    outs += 'sudo ip tuntap add mode tap name %(tap)s\n'    \
            'sudo ip link set %(tap)s up\n'                 \
            'sudo brctl addif %(br)s %(tap)s\n\n'           \
                % {'tap': tap, 'br': b}

    vms[vm]['ports'].append({'tap': tap, 'br': b, 'idx': idx,
                             'vlan': shim})


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


# Run the enrollment operations in an order which respect the dependencies
for dif in dif_ordering:
    for enrollment in enrollments[dif]:
        vm = vms[enrollment['enrollee']]

        print('I am going to enroll %s to DIF %s against neighbor %s, through '\
                'lower DIF %s' % (enrollment['enrollee'], dif,
                                  enrollment['enroller'],
                                  enrollment['lower_dif']))

        outs += 'sleep 2\n' # important!!
        outs += ''\
            'DONE=255\n'\
            'while [ $DONE != "0" ]; do\n'\
            '   ssh -p %(ssh)s %(username)s@localhost << \'ENDSSH\'\n'\
            'set -x\n'\
            'sudo enroll.py --lower-dif %(ldif)s --dif %(dif)s.DIF '\
                        '--ipcm-conf /etc/%(vmname)s.ipcm.conf '\
                        '--enrollee-name %(dif)s.%(id)s.IPCP '\
                        '--enroller-name %(dif)s.%(pvid)s.IPCP\n'\
            'sleep 1\n'\
            'true\n'\
            'ENDSSH\n'\
            '   DONE=$?\n'\
            '   if [ $DONE != "0" ]; then\n'\
            '       sleep 1\n'\
            '   fi\n'\
            'done\n\n' % {'ssh': vm['ssh'], 'id': vm['id'],
                          'pvid': vms[enrollment['enroller']]['id'],
                          'username': env_dict['username'],
                          'vmname': vm['name'],
                          'dif': dif, 'ldif': enrollment['lower_dif']}

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

for shim in sorted(shims):
    outs += 'sudo ip link set %(br)s down\n'        \
            'sudo brctl delbr %(br)s\n'             \
            '\n' % {'br': shims[shim]['bridge']}

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


for dif in difs:
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

    for policy in dif_policies[dif]:
        gen_templates.translate_policy(difconf, policy['path'], policy['ps'])


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

