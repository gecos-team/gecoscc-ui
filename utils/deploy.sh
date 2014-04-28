#!/bin/bash

yum install python-setuptools python-devel autoconf make gcc gettext

cat > /etc/yum.repos.d/Mongo10gen.repo << EOF
[mongodb]
name=MongoDB Repository
baseurl=http://downloads-distro.mongodb.org/repo/redhat/os/x86_64/
gpgcheck=0
enabled=0
EOF

yum install -enablerepo mongodb mongo-10gen mongo-10gen-server

chkconfig mongod on

useradd gecoscc --home /opt/gecoscc/

easy_install virtualenv
sudo -u gecoscc virtualenv /opt/gecoscc
sudo -u gecoscc /opt/gecoscc/bin/pip install https://pypi.python.org/packages/source/g/gevent/gevent-1.0.tar.gz

lokkit -s http
lokkit -s https
lokkit -p 6543:tcp

service mongod start

echo "Execute python setup.py develop in the gecoscc egg"
echo "You should start the http and celery servers with:"
echo "pserve config-templates/development.ini"
echo "pceleryd config-templates/development.ini"
