#!/bin/bash

set -o pipefail

# Bash script launching the the SlipStream application.
# The parameters are the cloud service chosen by the client
# and its Github repository (optional) following the SAR-proc model at
# https://github.com/SixSq/SAR-proc.
# Input data is stored in file list "product_list.cfg".

# Connector instance name as defined on https://nuv.la for which user has
# provided credentials in its profile.
trap 'rm -f $LOG' EXIT

LOG=`mktemp`
SS_ENDPOINT=https://nuv.la

python -u `which ss-execute` \
    --endpoint $SS_ENDPOINT \
    --wait 60 \
    --keep-running="never" \
    --parameters="
    ss-username=$SLIPSTREAM_USERNAME,
    ss-password=$SLIPSTREAM_PASSWORD" \
    EO_Sentinel_1/ELK-server 2>&1 | tee $LOG

#     run=`awk '/::: Waiting/ {print $7}' $LOG`
#     echo $run
#
# if [ "$?" == "0" ]; then
#     run=`awk '/::: Waiting/ {print $7}' $LOG`
#     echo $run
#     curl -u $SLIPSTREAM_USERNAME:$SLIPSTREAM_PASSWORD \
#         $run/machine:hostname
#     echo
# fi
