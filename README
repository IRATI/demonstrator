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
