#!/bin/bash

set -e
set -x

_ss_set_hostname() {
  echo "`ss-get hostname`    $(hostname)" >> /etc/hosts
  ss-set machine-hn `hostname`
}

_get_cloud_hostname() {
  server_ip=`ss-get hostname`
  server_hostname=`ss-get machine-hn`
}

_ss_set_hostname
_get_cloud_hostname

ss_username=`ss-get ss-username`
ss_password=`ss-get ss-password`

git clone https://github.com/SixSq/SAR-framework.git

pip install -r ~/SAR-framework/deployment/dmm/requirements.txt

cd ~/SAR-framework/deployment/dmm/
python server_dmm.py \
    $ss_username \
    $ss_password \
    $server_ip \
    $server_hostname &
