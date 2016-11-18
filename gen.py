#!/usr/bin/env python

#
# Author: Vincenzo Maffione <v.maffione@nextworks.it>
#

import multiprocessing
import gen_templates
import subprocess
import argparse
import json
import copy
import re
import os


def which(program):
    FNULL = open(os.devnull, 'w')
    retcode = subprocess.call(['which', program], stdout = FNULL,
                              stderr = subprocess.STDOUT)
    if retcode != 0:
        print('Fatal error: Cannot find "%s" program' % program)
        quit(1)


def dict_dump_json(file_name, dictionary, env_dict):
    dictionary_str = json.dumps(dictionary, indent = 4,
                                sort_keys = True) % env_dict
    fout = open(file_name, 'w')
    fout.write(dictionary_str);
    fout.close()


def joincat(haystack, needle):
    return ' '.join([needle, haystack])


def netem_validate(netem_args):
    ret = True

    try:
        fdevnull = open(os.devnull, 'w')
        subprocess.check_call('sudo ip tuntap add mode tap name tapiratiprobe'.split())
        subprocess.check_call(('sudo tc qdisc add dev '\
                               'tapiratiprobe root netem %s'\
                                % netem_args).split(), stdout=fdevnull,
                                stderr=fdevnull)
        fdevnull.close()
    except:
        ret = False

    subprocess.call('sudo ip tuntap del mode tap name tapiratiprobe'.split())

    return ret


description = "Python script to generate IRATI deployments for Virtual Machines"
epilog = "2016 Vincenzo Maffione <v.maffione@nextworks.it>"

argparser = argparse.ArgumentParser(description = description,
                                    epilog = epilog)
argparser.add_argument('-c', '--conf',
                       help = "gen.conf configuration file", type = str,
                       default = 'gen.conf')
argparser.add_argument('-g', '--graphviz', action='store_true',
                       help = "Generate DIF graphs with graphviz")
argparser.add_argument('--legacy', action='store_true',
                       help = "Use qcow2 image rather than buildroot ramfs")
argparser.add_argument('-m', '--memory',
                       help = "Amount of memory in megabytes", type = int,
                       default = '128')
argparser.add_argument('-e', '--enrollment-strategy',
                       help = "Minimal uses a spanning tree of each DIF",
                       type = str, choices = ['minimal', 'full-mesh', 'manual'],
                       default = 'minimal')
argparser.add_argument('--ring',
                       help = "Use ring topology with variable number of nodes",
                       type = int)
argparser.add_argument('--kernel',
                       help = "custom kernel buildroot image", type = str,
                       default = 'buildroot/bzImage')
argparser.add_argument('--initramfs',
                       help = "custom initramfs buildroot image", type = str,
                       default = 'buildroot/rootfs.cpio')
argparser.add_argument('-f', '--frontend',
                       help = "Choose which emulated NIC the nodes will use",
                       type = str, choices = ['virtio-net-pci', 'e1000'],
                       default = 'virtio-net-pci')
argparser.add_argument('--vhost', action='store_true',
                       help = "Use vhost acceleration for virtio-net frontend")
argparser.add_argument('--manager', action='store_true',
                       help = "Add support for NMS manager and dedicated LAN")
argparser.add_argument('--manager-kernel',
                       help = "custom kernel buildroot image for the manager",
                       type = str, default = 'buildroot/bzImage')
argparser.add_argument('--manager-initramfs',
                       help = "custom initramfs buildroot image for the manager",
                       type = str, default = 'buildroot/rootfs.cpio')
argparser.add_argument('--overlay',
                       help = "Overlay the specified directory in the generated image",
                       type = str)
argparser.add_argument('--loglevel',
                       help = "Set verbosity level",
                       choices = ['DBG', 'INFO', 'NOTE', 'WARN', 'ERR', 'CRIT', 'ALERT', 'EMERG'],
                       default = 'DBG')
args = argparser.parse_args()


which('brctl')
which('qemu-system-x86_64')

subprocess.call(['chmod', '0400', 'buildroot/irati_rsa'])

if args.overlay:
    args.overlay = os.path.abspath(args.overlay)
    if not os.path.isdir(args.overlay):
        args.overlay = None

if args.legacy:
    sshopts = ''
    sudo = 'sudo'
else:
    sshopts = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '\
              '-o IdentityFile=buildroot/irati_rsa'
    sudo = ''


if args.legacy:
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
env_dict['varpath'] = env_dict['installpath']


if not args.legacy:
    # overwrite vmimgpath, installpath, varpath, username
    env_dict['vmimgpath'] = args.initramfs
    env_dict['installpath'] = '/usr'
    env_dict['varpath'] = ''
    env_dict['username'] = 'root'


# Possibly autogenerate ring topology
if args.ring != None and args.ring > 0:
    print("Ignoring %s, generating ring topology" % (args.conf,))
    fout = open('ring.conf', 'w')
    for i in range(args.ring):
        i_next = i + 1
        if i_next == args.ring:
            i_next = 0
        fout.write('eth %(vlan)s 0Mbps m%(i)s m%(inext)s\n' % \
                    {'i': i+1, 'inext': i_next+1, 'vlan': i+1+100})
    for i in range(args.ring):
        i_prev = i - 1
        if i_prev < 0:
            i_prev = args.ring - 1
        fout.write('dif n m%(i)s %(vlan)s %(vprev)s\n' % \
                    {'i': i+1, 'vlan': i+1+100, 'vprev': i_prev+1+100})
    fout.close()
    args.conf = 'ring.conf'


# Some constants related to the RINA management
injected_lines = []
mgmt_shim_dif_name = '3456'
mgmt_dif_name = 'NMS'
mgmt_node_name = 'mgr'


############################# Parse gen.conf ##############################
fin = open(args.conf, 'r')

vms = dict()
shims = dict()
links = []
difs = dict()
enrollments = dict()
dif_policies = dict()
dif_graphs = dict()
app_mappings = []
overlays = dict()
netems = dict()
manual_enrollments = dict()

linecnt = 0
conf_injection = True

while 1:
    line = fin.readline()
    if line == '':
        # EOF, try to pick from injected lines
        if len(injected_lines) > 0:
            line = injected_lines.pop(0)

    if line == '':
        if not conf_injection:
            # Injection already done, let's stop now
            break
        # Inject new lines and continue
        conf_injection = False
        if args.manager:
            vm_list = [vmname for vmname in sorted(vms)]
            vm_list.append(mgmt_node_name)  # a VM for the manager
            injected_lines.append('eth %s 0Mbps %s' % (mgmt_shim_dif_name, ' '.join(vm_list)))
            for vmname in vm_list:
                injected_lines.append('dif %s %s %s' % (mgmt_dif_name, vmname, mgmt_shim_dif_name))
        continue

    linecnt += 1

    line = line.replace('\n', '')

    if line.startswith('#'):
        continue

    if re.match(r'\s*$', line):
        continue

    m = re.match(r'\s*eth\s+(\d+)\s+(\d+)([GMK])bps\s+(\w.*)$', line)
    if m:
        vlan = m.group(1)
        speed = int(m.group(2))
        speed_unit = m.group(3).lower()
        vm_list = m.group(4).split()

        if vlan in shims:
            print('Error: Line %d: shim %s already defined' \
                                            % (linecnt, vlan))
            continue

        shims[vlan] = {'bridge': 'rbr' + vlan, 'vlan': vlan, 'speed': speed,
                       'speed_unit': speed_unit}

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

    m = re.match(r'\s*policy\s+(\w+)\s+(\*|(?:(?:\w+,)*\w+))\s+([*\w.-]+)\s+([\w-]+)((?:\s+[\w.-]+\s*=\s*[\w.-]+)*)\s*$', line)
    if m:
        dif = m.group(1)
        nodes = m.group(2)
        path = m.group(3)
        ps = m.group(4)
        parms = list()
        if m.group(5) != None:
            parms_str = m.group(5).strip()
            if parms_str != '':
                parms = parms_str.split(' ')

        if dif not in dif_policies:
            dif_policies[dif] = []

        if nodes == '*':
            nodes = []
        else:
            nodes = nodes.split(',')

        dif_policies[dif].append({'path': path, 'nodes': nodes,
                                  'ps': ps, 'parms' : parms})
        if path not in gen_templates.policy_translator:
            print('Unknown component path "%s"' % path)
            quit(1)
        continue

    m = re.match(r'\s*appmap\s+(\w+)\s+([\w.]+)\s+(\d+)\s*$', line)
    if m:
        dif = m.group(1)
        apname = m.group(2)
        apinst = m.group(3)

        app_mappings.append({'name': '%s-%s--' % (apname, apinst), 'dif' : dif})

        continue

    m = re.match(r'\s*overlay\s+(\w+)\s+([\w.-/]+\s*$)', line)
    if m:
        vmname = m.group(1)
        opath = m.group(2)

        opath = os.path.abspath(opath)

        if not os.path.isdir(opath):
            print("Error: line %d: no such overlay path" % linecnt)
            continue

        overlays[vmname] = opath

        continue

    m = re.match(r'\s*netem\s+(\d+)\s+(\w+)\s+(\w.*)$', line)
    if m:
        dif = m.group(1)
        vmname = m.group(2)
        netem_args = m.group(3)

        if dif not in netems:
            netems[dif] = dict()
        netems[dif][vmname] = {'args': netem_args, 'linecnt': linecnt}

        continue

    m = re.match(r'\s*enroll\s+([\w.-]+)\s+([\w.-]+)\s+([\w.-]+)\s+([\w.-]+)\s*$', line)
    if m:
        if args.enrollment_strategy != 'manual':
            print('Warning: ignoring enroll directive at line %d' % linecnt)
            continue

        dif_name = m.group(1)
        enrollee = m.group(2)
        enroller = m.group(3)
        n_1_dif = m.group(4)

        if dif_name not in manual_enrollments:
            manual_enrollments[dif_name] = []
        manual_enrollments[dif_name].append({
                                   'enrollee': enrollee,
                                   'enroller': enroller,
                                   'lower_dif': n_1_dif,
                                   'linecnt': linecnt})
        continue

    print("Warning: line %d not recognized" % linecnt)

fin.close()

for dif in difs:
    if dif not in dif_policies:
        dif_policies[dif] = []

boot_batch_size = max(1, multiprocessing.cpu_count() / 2)
wait_for_boot = 12  # in seconds
if len(vms) > 8:
    print("You want to run a lot of nodes, so it's better if I give "
          "each node some time to boot (since the boot is CPU-intensive)")

############ Compute registration/enrollment order for DIFs ###############

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
    dif_graphs[dif] = dict()
    first = None

    # For each N-1-DIF supporting this DIF, compute the set of nodes that
    # share such N-1-DIF. This set will be called the 'neighset' of
    # the N-1-DIF for the current DIF.

    for vmname in difs[dif]:
        dif_graphs[dif][vmname] = [] # init for later use
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
                    dif_graphs[dif][vm1].append((vm2, lower_dif))

    enrollments[dif] = []

    if args.manager and dif == mgmt_dif_name:
        # Enrollment in the NMS DIF is managed as a special case:
        # each node is enrolled against the manager node
        for vmname in vms:
            if vmname != mgmt_node_name:
                enrollments[dif].append({'enrollee': vmname,
                                         'enroller': mgmt_node_name,
                                         'lower_dif': mgmt_shim_dif_name})

    elif args.enrollment_strategy == 'minimal':
        # To generate the list of enrollments, we simulate one,
        # using breadth-first trasversal.
        enrolled = set([first])
        frontier = set([first])
        while len(frontier):
            cur = frontier.pop()
            for edge in dif_graphs[dif][cur]:
                if edge[0] not in enrolled:
                    enrolled.add(edge[0])
                    enrollments[dif].append({'enrollee': edge[0],
                                             'enroller': cur,
                                             'lower_dif': edge[1]})
                    frontier.add(edge[0])

    elif args.enrollment_strategy == 'full-mesh':
        for cur in dif_graphs[dif]:
            for edge in dif_graphs[dif][cur]:
                if cur < edge[0]:
                    enrollments[dif].append({'enrollee': cur,
                                             'enroller': edge[0],
                                             'lower_dif': edge[1]})

    elif args.enrollment_strategy == 'manual':
        if dif not in manual_enrollments:
            continue

        for e in manual_enrollments[dif]:
            if e['enrollee'] not in difs[dif]:
                print('Warning: ignoring line %d because VM %s does '\
                      'not belong to DIF %s' % (e['linecnt'],
                      e['enrollee'],  dif))
                continue

            if e['enroller'] not in difs[dif]:
                print('Warning: ignoring line %d because VM %s does '\
                      'not belong to DIF %s' % (e['linecnt'],
                      e['enroller'],  dif))
                continue

            if e['lower_dif'] not in neighsets or \
                    e['enrollee'] not in neighsets[e['lower_dif']]:
                print('Warning: ignoring line %d because VM %s cannot '\
                      'use N-1-DIF %s' % (e['linecnt'], e['enrollee'],
                                          e['lower_dif']))
                continue

            if e['lower_dif'] not in neighsets or \
                    e['enroller'] not in neighsets[e['lower_dif']]:
                print('Warning: ignoring line %d because VM %s cannot '\
                      'use N-1-DIF %s' % (e['linecnt'], e['enroller'],
                                          e['lower_dif']))
                continue

            enrollments[dif].append(e)

    else:
        # This is a bug
        assert(False)

    #print(neighsets)
    #print(dif_graphs[dif])

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

    if shims[shim]['speed'] > 0:
        speed = '%d%sbit' % (shims[shim]['speed'], shims[shim]['speed_unit'])
        if shim not in netems:
            netems[shim] = dict()
        if vm not in netems[shim]:
            netems[shim][vm] = {'args': '', 'linecnt': 0}

        # Rate limit the traffic transmitted on the TAP interface
        netems[shim][vm]['args'] += ' rate %s' % (speed,)

    if shim in netems:
        if vm in netems[shim]:
            if not netem_validate(netems[shim][vm]['args']):
                print('Warning: line %(linecnt)s is invalid and '\
                      'will be ignored' % netems[shim][vm])
                continue
            outs += 'sudo tc qdisc add dev %(tap)s root netem '\
                    '%(args)s\n'\
                    % {'tap': tap, 'args': netems[shim][vm]['args']}

    vms[vm]['ports'].append({'tap': tap, 'br': b, 'idx': idx,
                             'vlan': shim})


vmid = 1
budget = boot_batch_size

for vmname in sorted(vms):
    vm = vms[vmname]

    vm['id'] = vmid

    fwdp = env_dict['baseport'] + vmid
    fwdc = fwdp + 10000
    mac = '00:0a:0a:0a:%02x:%02x' % (vmid, 99)

    vm['ssh'] = fwdp

    vars_dict = {'fwdp': fwdp, 'id': vmid, 'mac': mac,
                 'vmimgpath': env_dict['vmimgpath'], 'fwdc': fwdc,
                 'memory': args.memory, 'kernel': args.kernel,
                 'frontend': args.frontend}

    if vmname == mgmt_node_name:
        vars_dict['vmimgpath'] = args.manager_initramfs
        vars_dict['kernel'] = args.manager_kernel

    outs += 'qemu-system-x86_64 '
    if not args.legacy:
        outs += '-kernel %(kernel)s '                                   \
                '-append "console=ttyS0" '                              \
                '-initrd %(vmimgpath)s '                                \
                '-nographic ' % vars_dict
    else:
        outs += '"%(vmimgpath)s" '                                      \
                '-snapshot '                                            \
                '-serial tcp:127.0.0.1:%(fwdc)s,server,nowait '         \
                                % vars_dict

    outs += '-display none '                                            \
            '--enable-kvm '                                             \
            '-smp 2 '                                                   \
            '-m %(memory)sM '                                           \
            '-device %(frontend)s,mac=%(mac)s,netdev=mgmt '                    \
            '-netdev user,id=mgmt,hostfwd=tcp::%(fwdp)s-:22 '           \
            '-vga std '                                                 \
            '-pidfile rina-%(id)s.pid '                                 \
                        % vars_dict

    del vars_dict

    for port in vm['ports']:
        tap = port['tap']
        mac = '00:0a:0a:0a:%02x:%02x' % (vmid, port['idx'])
        port['mac'] = mac

        outs += ''                                                      \
        '-device %(frontend)s,mac=%(mac)s,netdev=data%(idx)s '                 \
        '-netdev tap,ifname=%(tap)s,id=data%(idx)s,script=no,downscript=no'\
        '%(vhost)s '\
            % {'mac': mac, 'tap': tap, 'idx': port['idx'],
               'frontend': args.frontend,
               'vhost': ',vhost=on' if args.vhost else ''}

    outs += '&\n\n'

    budget -= 1
    if budget <= 0:
        outs += 'sleep %s\n' % wait_for_boot
        budget = boot_batch_size

    vmid += 1


for vmname in sorted(vms):
    vm = vms[vmname]

    gen_files_conf = 'shimeth.%(name)s.*.dif da.map %(name)s.ipcm.conf' % {'name': vmname}
    if any(vmname in difs[difname] for difname in difs):
        gen_files_conf = joincat(gen_files_conf, 'normal.%(name)s.*.dif' % {'name': vmname})
    gen_files_bin = 'enroll.py'
    overlay = ''
    per_vm_overlay = ''

    if args.legacy:
        gen_files_bin = joincat(gen_files_bin, 'mac2ifname')

    if args.overlay:
        overlay = args.overlay

    if vmname in overlays:
        per_vm_overlay = overlays[vmname]

    ipcm_components = ['scripting', 'console']
    if args.manager:
        ipcm_components.append('mad')
    ipcm_components = ', '.join(ipcm_components)

    gen_files = ' '.join([gen_files_conf, gen_files_bin, overlay, per_vm_overlay])

    outs += ''\
            'DONE=255\n'\
            'while [ $DONE != "0" ]; do\n'\
            '   scp %(sshopts)s -r -P %(ssh)s %(genfiles)s %(username)s@localhost: \n'\
            '   DONE=$?\n'\
            '   if [ $DONE != "0" ]; then\n'\
            '       sleep 1\n'\
            '   fi\n'\
            'done\n\n'\
            'ssh %(sshopts)s -p %(ssh)s %(username)s@localhost << \'ENDSSH\'\n'\
                'set -x\n'\
                'SUDO=%(sudo)s\n'\
                '$SUDO hostname %(name)s\n'\
                '\n'\
                '$SUDO mv %(genfilesconf)s /etc\n'\
                '$SUDO mv %(genfilesbin)s /usr/bin\n'\
            '\n' % {'name': vm['name'], 'ssh': vm['ssh'], 'id': vm['id'],
                    'username': env_dict['username'],
                    'genfiles': gen_files, 'genfilesconf': gen_files_conf,
                    'genfilesbin': gen_files_bin, 'vmname': vm['name'],
                    'sshopts': sshopts, 'sudo': sudo}

    for ov in [overlay, per_vm_overlay]:
        if ov != '':
            outs += '$SUDO cp -r %(ov)s/* /\n'\
                    '$SUDO rm -rf %(ov)s\n'\
                        % {'ov': os.path.basename(ov)}

    for port in vm['ports']:
        outs += 'PORT=$(mac2ifname %(mac)s)\n'\
                '$SUDO ip link set $PORT up\n'\
                '$SUDO ip link add link $PORT name $PORT.%(vlan)s type vlan id %(vlan)s\n'\
                '$SUDO ip link set $PORT.%(vlan)s up\n'\
                '$SUDO sed -i "s|ifc%(idx)s|$PORT|g" /etc/shimeth.%(vmname)s.%(vlan)s.dif\n'\
                    % {'mac': port['mac'], 'idx': port['idx'],
                       'id': vm['id'], 'vlan': port['vlan'],
                       'vmname': vm['name']}

    if args.legacy:
        outs +=     '$SUDO modprobe shim-eth-vlan\n'\
                    '$SUDO modprobe normal-ipcp\n'
    outs +=     '$SUDO modprobe rina-default-plugin\n'\
                '$SUDO %(installpath)s/bin/ipcm -a \"%(ipcmcomps)s\" '\
                            '-c /etc/%(vmname)s.ipcm.conf -l %(verb)s &> log &\n'\
                'sleep 1\n'\
                'true\n'\
            'ENDSSH\n' % {'installpath': env_dict['installpath'],
                          'vmname': vm['name'], 'verb': args.loglevel,
                          'ipcmcomps': ipcm_components}


# Run the enrollment operations in an order which respect the dependencies
for dif in dif_ordering:
    for enrollment in enrollments[dif]:
        vm = vms[enrollment['enrollee']]

        print('I am going to enroll %s to DIF %s against neighbor %s, through '\
                'lower DIF %s' % (enrollment['enrollee'], dif,
                                  enrollment['enroller'],
                                  enrollment['lower_dif']))

        if enrollment['lower_dif'] not in shims:
            enrollment['lower_dif'] = enrollment['lower_dif'] + '.DIF'

        outs += 'sleep 2\n' # important!!
        outs += ''\
            'DONE=255\n'\
            'while [ $DONE != "0" ]; do\n'\
            '   ssh %(sshopts)s -p %(ssh)s %(username)s@localhost << \'ENDSSH\'\n'\
            'set -x\n'\
            'SUDO=%(sudo)s\n'\
            '$SUDO enroll.py --lower-dif %(ldif)s --dif %(dif)s.DIF '\
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
                          'dif': dif, 'ldif': enrollment['lower_dif'],
                          'sshopts': sshopts, 'sudo': sudo}

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

# If some app directives were specified, use those to build da.map.
# Otherwise, assume the standard applications are to be mapped in
# the DIF with the highest rank.
if len(app_mappings) == 0:
    if len(dif_ordering) > 0:
        for adm in gen_templates.da_map_base["applicationToDIFMappings"]:
            adm["difName"] = "%s.DIF" % (dif_ordering[-1],)
else:
    gen_templates.da_map_base["applicationToDIFMappings"] = []
    for apm in app_mappings:
        gen_templates.da_map_base["applicationToDIFMappings"].append({
                                                    "encodedAppName": apm['name'],
                                                    "difName": "%s.DIF" % (apm['dif'])
                                            })

if args.manager:
    # Add MAD/Manager configuration
    gen_templates.ipcmconf_base["addons"] = {
                    "mad": {
                            "managerAppName": "",
                            "NMSDIFs" : [{"DIF" : "%s.DIF" % (mgmt_dif_name)}],
                            "managerConnections" : [ {
                                        "managerAppName" : "manager-1--",
                                        "DIF": "%s.DIF" % (mgmt_dif_name)
                                    }
                                ]
                    }
                }

for vmname in vms:
    ipcmconfs[vmname] = copy.deepcopy(gen_templates.ipcmconf_base)
    if args.manager:
        ipcmconfs[vmname]["addons"]["mad"]["managerAppName"] = "%s.mad-1--" % (vmname)

difconfs = dict()
for dif in difs:
    difconfs[dif] = dict()
    for vmname in difs[dif]:
        difconfs[dif][vmname] = copy.deepcopy(gen_templates.normal_dif_base)

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


# Run over dif_ordering array, to make sure each IPCM config has
# the correct ordering for the ipcProcessesToCreate list of operations.
# If we iterated over the difs map, the order would be randomic, and so
# some IPCP registrations in lower DIFs may fail. This would happen because
# at the moment of registration, it may be that the IPCP of the lower DIF
# has not been created yet.
for dif in dif_ordering:

    if dif in shims:
        # Shims are managed separately, in the previous loop
        continue

    for vmname in difs[dif]:
        vm = vms[vmname]
        ipcmconf = ipcmconfs[vmname]

        normal_ipcp = { "apName": "%s.%d.IPCP" % (dif, vm['id']),
                        "apInstance": "1",
                        "difName": "%s.DIF" % (dif,) }

        normal_ipcp["difsToRegisterAt"] = []
        for lower_dif in difs[dif][vmname]:
            if lower_dif not in shims:
                lower_dif = lower_dif + '.DIF'
            normal_ipcp["difsToRegisterAt"].append(lower_dif)

        ipcmconf["ipcProcessesToCreate"].append(normal_ipcp)

        ipcmconf["difConfigurations"].append({
                                "name": "%s.DIF" % (dif,),
                                "template": "normal.%s.%s.dif" % (vmname, dif,)
                                })

        # Fill in the map of IPCP addresses. This could be moved at difconfs
        # deepcopy-time
        for ovm in difs[dif]:
            difconfs[dif][ovm]["knownIPCProcessAddresses"].append({
                                        "apName":  "%s.%d.IPCP" % (dif, vm['id']),
                                        "apInstance": "1",
                                        "address": 16 + vm['id']
                                    })

        for policy in dif_policies[dif]:
            if policy['nodes'] == [] or vmname in policy['nodes']:
                gen_templates.translate_policy(difconfs[dif][vmname], policy['path'],
                                               policy['ps'], policy['parms'])


# Dump the DIF Allocator map
dict_dump_json('da.map', gen_templates.da_map_base, env_dict)

for vmname in vms:
    # Dump the IPCM configuration files
    dict_dump_json('%s.ipcm.conf' % (vmname,), ipcmconfs[vmname], env_dict)

for dif in difs:
    for vmname in difs[dif]:
        # Dump the normal DIF configuration files
        dict_dump_json('normal.%s.%s.dif' % (vmname, dif,),
                       difconfs[dif][vmname], env_dict)


# Dump the mapping from nodes to SSH ports
fout = open('gen.map', 'w')
for vmname in sorted(vms):
    fout.write('%s %d\n' % (vmname, env_dict['baseport'] + vms[vmname]['id']))
fout.close()


if args.graphviz:
    try:
        import pydot

        colors = ['red', 'green', 'blue', 'orange', 'yellow']
        fcolors = ['black', 'black', 'white', 'black', 'black']

        gvizg = pydot.Dot(graph_type = 'graph')
        i = 0
        for dif in difs:
            for vmname in dif_graphs[dif]:
                node = pydot.Node(dif + vmname,
                                  label = "%s(%s)" % (vmname, dif),
                                  style = "filled", fillcolor = colors[i],
                                  fontcolor = fcolors[i])
                gvizg.add_node(node)

            for vmname in dif_graphs[dif]:
                for (neigh, lower_dif) in dif_graphs[dif][vmname]:
                    if vmname > neigh:
                        # Use lexicographical filter to avoid duplicate edges
                        continue

                    color = 'black'
                    # If enrollment is going to happen on this edge, color
                    # it in red
                    for enrollment in enrollments[dif]:
                        ee = enrollment['enrollee']
                        er = enrollment['enroller']
                        lo = enrollment['lower_dif']
                        if lo.endswith(".DIF"):
                            lo = lo[:-4]
                        if lower_dif == lo and \
                                ((vmname == ee and neigh == er) or \
                                (vmname == er and neigh == ee)):
                            color = 'red'
                            break

                    edge = pydot.Edge(dif + vmname, dif + neigh,
                                      label = lower_dif, color = color)
                    gvizg.add_edge(edge)

            i += 1
            if i == len(colors):
                i = 0

        gvizg.write_png('difs.png')
    except:
        print("Warning: pydot module not installed, cannot produce DIF "\
              "graphs images")

