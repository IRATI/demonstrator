###############################################################################
# 1. INTRODUCTION                                                             #
###############################################################################

This repository contains a command-line tool (gen.py) which allows the user to
try and test the IRATI in a multi-node scenario with the minimum possible
effort.

Each node is emulated using a light Virtual Machine (VM), run under the control
of the QEMU hypervisor. All the VMs are run locally without any risk for your
PC, so you don't need a dedicated machine or multiple physical machines.

All the user has to do is to prepare a configuration file which describes the
scenario to be demonstrated. This requires the user to specify all the Layer 2
connections between the nodes and all the DIFs which lay over this L2 topology.
A DIF can be stacked over other DIFs, and arbitrary level of recursion is
virtually supported by the tool (Be aware that the IRATI stack may place
restrictions on the recursion depth, so the scenario bootstrap may fail).

The syntax of the configuration file is detailed in section 3.

Once the configuration file has been prepared, the user can invoke the tool

    $ ./gen.py -c /path/to/config/file

which will generate two bash scripts: up.sh and down.sh.

Running the up.sh script will bootstrap the specified scenario, which involves
the following operations:

* Create TAP interfaces and linux software-bridges to emulate the
  specified L2 topology.

* Run the VMs emulating the nodes.

* Bootstrap the IRATI stack on each node, with proper configuration
  (IPCM configuration, DIF templates, DIF Allocator map, ...)

* Perform all the enrollment, at all DIF layers, respecting the
  dependency order.

The up.sh script reports verbose information about ongoing operations. If
everything goes well, you should be able to see the script reporting about
successful enrollment operations right before terminating.

Once the bootstrap is complete, the user can access any node an play with
them (e.g. running the rina-echo-time test application to check connectivity
between the nodes).

The tool can work in two different modes: buildroot (default) and legacy. The
way you access the nodes depends on the modes. In any case, unless you know
what you are doing, you want to use the default buildroot mode. More
information about the legacy mode can be found in section 5.

To undo the operations carried out by the up.sh, the user can run the down.sh
script. Once the latter script terminates, all the VMs have been terminated.

The user can run up.sh/down.sh multiple times, and use gen.py only when she
wants to modify the scenario. If you run up.sh, make sure you run down.sh
before generating a new scenario, otherwise a PC reboot may be necessary in
order to clean-up leftover artifacts.

By default, every VM is assigned 128 MB of memory, so with 4GB or memory you
can run topologies with up to 32 nodes. You may even try to reduce the per-VM
memory more, to achieve higher density.


###############################################################################
# 2. HARDWARE AND SOFTWARE REQUIREMENTS                                       #
###############################################################################

* [HW] An x86\_64 processor with hardware-assisted virtualization support (e.g.
  Intel VT-X or AMD-V)

* [SW] Linux-based Operating System.

* [SW] QEMU, a fast and portable machine emulator.

* [SW] brctl command-lilne tool (usually found in a distro package called
  bridge-utils or brctl).


###############################################################################
# 3. SCENARIO CONFIGURATION FILE SYNTAX                                       #
###############################################################################


###############################################################################
# 4. BUILDROOT MODE                                                           #
###############################################################################

When in buildroot (default) mode everything is straightforward, so there is
little to say.

Once you have run up.sh, you can access VM $K using

    $ ./access.sh $K

where $K is a positive integer which identifies the VM.

Each VMs runs in a minimal environment, which is an initramfs created using the
buildroot framework (https://buildroot.org/). All the IRATI software and its
dependencies are packed in less than 30 MB.

Any modifications done on the VM filesystem is discarded when the scenario is
torn down.


###############################################################################
# 5. LEGACY MODE                                                              #
###############################################################################

In short, don't use this mode unless you know what you are doing.

In addition to the requirements specified in section 2, you need a QEMU VM
image containing:
    - the IRATI stack installed
    - python
    - sudo enabled for the login username on the VM (referred to as
      ${username} in the following), with NOPASSWD, e.g. /etc/sudoers
      should contain something similar to the following line:
            %wheel ALL=(ALL) NOPASSWD: ALL


Instructions, to be followed in the specified order:

1. Edit the gen.env file to set the IRATI installation path (on the VM
   filesystem), the path of the QEMU VM image (on your physical machine
   file system) and the login username on the VM (${username})

2. Specify the desired topology in gen.conf

3. Run ./gen.py to generate bootstrap and teardown script for the
  topology specified in (2)

4. Use ./up.sh to bootstrap the scenario

5. VMs are accessible at localhost ports 2223, 2224, 2225, etc.
   e.g. ssh -p2223 ${username}@localhost

6. Perform your tests on the VMs using ssh (5)

7. Shutdown the scenario (destroying the VMs) using ./down.sh

8. VMs launched by ./up.sh have a non-persistent disk --> modifications
   will be lost at shutdown time (7).
   To make persistent modifications to the VM image (e.g. to update PRISTINE
   software), run ./update\_vm.sh and access the VM at
        ssh -p2222 ${username}@localhost

Don't try to run ./update\_vm.sh while the test is running (i.e. you've run
./up.sh but still not run ./down.sh).


In order to automatically login to the VMs, it's highly recommended to use SSH
keys. In this way it is possible to avoid inserting the password again and
again (during the tests):

    $ ./update_vm.sh
    $ ssh-keygen -t rsa  # e.g. save the key in /home/${username}/.ssh/pristine_rsa
    $ ssh-copy-id -p2222 ${username}@localhost
    shutdown the VM

[http://serverfault.com/questions/241588/how-to-automate-ssh-login-with-password]

Now you should be able to run ./up.sh without the need to insert the password


###############################################################################
# 6. CREDITS                                                                  #
###############################################################################

This tool has been developed on behalf of FP7 PRISTINE and H2020 ARCIFIRE EU
projects.

Author:
* Vincenzo Maffione <v DOT maffione AT nextworks DOT it>

Contributors:
* None yet :)
