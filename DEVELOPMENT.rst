===========
DEVELOPMENT
===========

Dependences
===========

Ubuntu dependeces, in another distro the names can change

::


    sudo apt-get install git
    sudo apt-get install python-setuptools
    sudo apt-get install python-dev
    sudo apt-get install libssl-dev
    sudo apt-get install mongodb

    sudo easy_install pip
    sudo pip install virtualenv


Install
=======

::

    git clone git@github.com:gecos-team/gecoscc-ui.git
    cd gecos-team
    virtualenv vgecoscc-ui
    source vgecoscc-ui/bin/activate
    python setup.py develop


Configure GECOSCC with a Chef server
====================================

admin.pem file is the pem of the chef administrator, you should get it from the Chef server machine

0. Enable virtual enviroment

::

    source vgecoscc-ui/bin/activate

1. Create an administrator

::

    pmanage config-templates/development.ini create_chef_administrator -u new_admin -e new_admin@example.com -a admin -k admin.pem -n -s

2. Import policies

::

    pmanage config-templates/development.ini import_policies -a admin -k chef-server/admin.pem

3. Update printers

::

    pmanage config-templates/development.ini update_printers

4. Synchronize repositories

::

    pmanage config-templates/development.ini synchronize_repositories

5. Create software profiles

::

    pmanage config-templates/development.ini create_software_profiles


Run server
==========  

::

    source vgecoscc-ui/bin/activate
    pserve config-templates/development.ini


Run test
========

::

    source vgecoscc-ui/bin/activate
    python setup.py test


Run test (with coverage)
========================


::

    source vgecoscc-ui/bin/activate
    python setup.py develop
    pip install -r test_requirements.txt
    vgecoscc-ui/bin/nosetests   --cover-html --cover-html-dir=/tmp/report

