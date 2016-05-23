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

    - Create TAP interfaces and linux software-bridges to emulate the
      specified L2 topology.

    - Run the VMs emulating the nodes.

    - Bootstrap the IRATI stack on each node, with proper configuration
      (IPCM configuration, DIF templates, DIF Allocator map, ...)

    - Perform all the enrollment, at all DIF layers, respecting the
      dependency order.

The up.sh script reports verbose information about ongoing operations. If
everything goes well, you should be able to see the script reporting about
successful enrollment operations right before terminating.

Once the bootstrap is complete, the user can access any node an play with
them (e.g. running the rina-echo-time test application to check connectivity
between the nodes).

To undo the operations carried out by the up.sh, the user can run the down.sh
script. Once the latter script terminates, the VMs have been terminated.


###############################################################################
# 2. HARDWARE AND SOFTWARE REQUIREMENTS                                       #
###############################################################################

  - An x86\_64 processor with hardware-assisted virtualization support (e.g.
    Intel VT-X or AMD-V)

  - Linux-based Operating System.

  - QEMU, a fast and portable machine emulator.

  - brctl command-lilne tool (usually found in a distro package called
    bridge-utils or brctl).


###############################################################################
# 3. SCENARIO CONFIGURATION FILE SYNTAX                                       #
###############################################################################


###############################################################################
# 4. BUILDROOT MODE                                                           #
###############################################################################


###############################################################################
# 5. LEGACY MODE                                                              #
###############################################################################

In short, don't use this mode unless you know what you are doing.

####### Requirements #######

- QEMU
- brctl command line tool (can be found in distro packages like
  bridge-utils)
- QEMU VM image containing:
    - the IRATI stack installed in
    - python
    - sudo enabled for the login username on the VM (referred to as
      ${username} in the following), with NOPASSWD, e.g. /etc/sudoers
      should contain something similar to the following line:
            %wheel ALL=(ALL) NOPASSWD: ALL


####### Instructions - please follow the specified order ########

(1) Edit the gen.env file to set the IRATI installation path (on the VM
    filesystem), the path of the QEMU VM image (on your physical machine
    file system) and the login username on the VM (${username})

(2) Specify the desired topology in gen.conf

(3) Run ./gen.py to generate bootstrap and teardown script for the
    topology specified in (2)

(4) Use ./up.sh to bootstrap the scenario

(5) VMs are accessible at localhost ports 2223, 2224, 2225, etc.
	e.g. ssh -p2223 ${username}@localhost

(6) Perform your tests on the VMs using ssh (5)

(7) Shutdown the scenario (destroying the VMs) using ./down.sh

(8) VMs launched by ./up.sh have a non-persistent disk --> modifications
     will be lost at shutdown time (7).
     To make persistent modifications to the VM image (e.g. to update PRISTINE
     software), run ./update_vm.sh and access the VM at
          ssh -p2222 ${username}@localhost

     Don't try to run ./update_vm.sh while the test is running (i.e. you've run
     ./up.sh but still not run ./down.sh).


####### Autologin to the VMs #######

It's highly recommended to use SSH keys to avoid inserting the password again
and again (during the tests):

    (a.1) $ ./update_vm.sh
    (a.2) $ ssh-keygen -t rsa  # e.g. save the key in /home/${username}/.ssh/pristine_rsa
    (a.3) $ ssh-copy-id -p2222 ${username}@localhost
    (a.4) shutdown the VM

[http://serverfault.com/questions/241588/how-to-automate-ssh-login-with-password]

Now you should be able to run ./up.sh without the need to insert the password


Vincenzo
