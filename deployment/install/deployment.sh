#!/bin/bash

set -e
set -x

ss_username=`ss-get ss-username`
ss_password=`ss-get ss-password`

git clone https://github.com/SixSq/SAR-framework.git

pip install -r ~/SAR-framework/deployment/dmm/requirements.txt

cd ~/SAR-framework/deployment/dmm/
python server_dmm.py \
    $ss_username \
    $ss_password &
