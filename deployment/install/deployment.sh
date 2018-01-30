#!/bin/bash

set -e
set -x

ss_username=`ss-get ss-username`
ss_password=`ss-get ss-password`

SAR_PATH=~/SAR-framework

git clone https://github.com/SixSq/SAR-framework.git $SAR_PATH

pip install -r $SAR_PATH/deployment/dmm/requirements.txt

cd $SAR_PATH/deployment/dmm/
python server_dmm.py \
    $ss_username \
    $ss_password &

# FIXME: remove when SS client is running in virtualenv.
pip install slipstream-client

url=http://$(ss-get hostname)
ss-set url.service "${url}"
ss-set ss:url.service "${url}"
