#!/bin/bash

set -e
set -x

ss_username=`ss-get ss-username`
ss_password=`ss-get ss-password`
ss-set ss-password undefined
hostip=$(ss-get hostname)
hostname=$(hostname)

SAR_PATH=~/SAR-framework

git clone https://github.com/SixSq/SAR-framework.git $SAR_PATH

pip install -r $SAR_PATH/app/dmm/requirements.txt

cd $SAR_PATH/app/dmm/
sed -i -e 's/<SS_USERNAME>/'$ss_username'/' \
       -e 's/<SS_PASSWORD>/'$ss_password'/' \
       -e 's/<DMM_IP>/'$hostip'/' \
       -e 's/<DMM_HOSTNAME>/'$hostname'/' \
       dmm.conf
python server_dmm.py &

# FIXME: remove when SS client is running in virtualenv.
pip install slipstream-client

url=http://$hostip
ss-set url.service "${url}"
ss-set ss:url.service "${url}"
