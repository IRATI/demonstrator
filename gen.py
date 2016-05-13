#!/usr/bin/env python

#
# Author: Vincenzo Maffione <v.maffione@nextworks.it>
#

import subprocess
import json
import copy
import re
import os


# Compile mac2ifname program
try:
    subprocess.call(['cc', '-Wall', '-o', 'mac2ifname', 'mac2ifname.c'])
except:
    print('Cannot find a C compiler to compile mac2ifname program')
    quit(1)

env_dict = {}
keywords = ['vmimgpath', 'installpath', 'username', 'baseport']

# Parse gen.env
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

# Parse gen.conf
fin = open('gen.conf', 'r')

vms = dict()
bridges = dict()
links = []

while 1:
    line = fin.readline()
    if line == '':
        break

    line = line.replace('\n', '')

    if line.startswith('#'):
        continue

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

for i in sorted(vms):
    vm = vms[i]

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

for i in sorted(vms):
    vm = vms[i]

    generated_files = 'enroll.py shimeth.%(name)s.*.dif default.dif '   \
                      '%(name)s.ipcm.conf mac2ifname' % {'name': vm['name']}

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
                'sudo sed -i "s|vmid|%(id)s|g" /etc/template.conf\n'\
            '\n' % {'name': vm['name'], 'ssh': vm['ssh'], 'id': vm['id'],
                    'username': env_dict['username'],
                    'genfiles': generated_files}

    for port in vm['ports']:
        outs += 'PORT=$(mac2ifname %(mac)s)\n'\
                'sudo ip link set $PORT up\n'\
                'sudo ip link add link $PORT name $PORT.%(vlan)s type vlan id %(vlan)s\n'\
                'sudo ip link set $PORT.%(vlan)s up\n'\
                'sudo sed -i "s|ifc%(idx)s|$PORT|g" /etc/shimeth%(idx)s.dif\n'\
                'sudo sed -i "s|vlan%(idx)s|%(vlan)s|g" /etc/template.conf\n'\
                    % {'mac': port['mac'], 'idx': port['idx'],
                       'id': vm['id'], 'vlan': port['vlan']}

    outs +=     'sudo modprobe shim-eth-vlan\n'\
                'sudo modprobe normal-ipcp\n'\
                'sudo modprobe rina-default-plugin\n'\
                'sudo %(installpath)s/bin/ipcm -a "scripting, console, mad" -c /etc/template.conf -l DEBUG &> log &\n'\
                'sleep 1\n'\
                'true\n'\
            'ENDSSH\n' % env_dict


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
            'sudo enroll.py %(vlan)s %(pvid)s\n'\
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
                          'username': env_dict['username']}

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

for i in sorted(vms):
    vm = vms[i]
    outs += 'kill_qemu rina-%(id)s.pid\n' % {'id': vm['id']}

outs += '\n'

for i in sorted(vms):
    vm = vms[i]
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

# Generate the IPCM configuration files
ipcmconf_base = {
            "configFileVersion": "1.4.1",
            "localConfiguration": {
                "installationPath": "%(installpath)s/bin",
                "libraryPath": "%(installpath)s/lib",
                "logPath": "%(installpath)s/var/log",
                "consoleSocket": "%(installpath)s/var/run/ipcm-console.sock",
                "pluginsPaths": [
                        "%(installpath)s/lib/rinad/ipcp",
                        "/lib/modules/4.1.10-irati/extra"
                ]
                },

            "applicationToDIFMappings": [
                {
                    "encodedAppName": "rina.apps.echotime.server-1--",
                    "difName": "n.DIF"
                },
                {
                    "encodedAppName": "rina.apps.echotime.client-1--",
                    "difName": "n.DIF"
                },
                {
                    "encodedAppName": "rina.apps.echotime-2--",
                    "difName": "n.DIF"
                },
                {
                    "encodedAppName": "rina.apps.echotime.client-2--",
                    "difName": "n.DIF"
                }
            ],

            "ipcProcessesToCreate": [],
            "difConfigurations": [],
        }

for i in sorted(vms):
    vm = vms[i]

    ipcmconf = copy.deepcopy(ipcmconf_base)

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


    normal_ipcp = { "apName": "n.1.%d.IPCP" % vm['id'],
                    "apInstance": "1",
                    "difName": 'n.DIF' }

    normal_ipcp["difsToRegisterAt"] = []
    for port in vm['ports']:
        normal_ipcp["difsToRegisterAt"].append(port['vlan'])
    ipcmconf["ipcProcessesToCreate"].append(normal_ipcp)

    ipcmconf["difConfigurations"].append({
                            "name": "n.DIF",
                            "template": "default.DIF"
                            })

    # Dump the IPCM configuration files
    ipcmconf_str = json.dumps(ipcmconf, indent=4, sort_keys=True) % env_dict
    fout = open('%s.ipcm.conf' % (vm['name'],), 'w')
    fout.write(ipcmconf_str);
    fout.close()

