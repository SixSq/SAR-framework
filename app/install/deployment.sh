#!/bin/bash

set -e
set -x

ss_password=`ss-get ss-password`
ss-set ss-password undefined
ss_username=`ss-get ss-username`
hostip=$(ss-get hostname)
hostname=$(hostname)

SAR_LOC=~/SAR-framework

git clone https://github.com/SixSq/SAR-framework.git $SAR_LOC

pip install -r $SAR_LOC/app/dmm/requirements.txt

cd $SAR_LOC/app/dmm/
sed -i -e 's/<SS_USERNAME>/'$ss_username'/' \
       -e 's/<SS_PASSWORD>/'$ss_password'/' \
       -e 's/<DMM_IP>/'$hostip'/' \
       -e 's/<DMM_HOSTNAME>/'$hostname'/' \
       dmm.conf
python server_dmm.py &

# FIXME: remove when SS client is running in virtualenv.
pip install slipstream-client

url=http://$hostip/dmm
ss-set url.service "${url}"
ss-set ss:url.service "${url}"
