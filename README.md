SENTINEL-1 (SAR) framework
==========================

This repo consists of a SAR product generation infrastructure designed for SLA
enforcement. It is packaged in an Nuvla application. Its image processing job
are done via the call of a relative app namely [SAR_app](https://github.com/SixSq/SAR-app).
The main run starts an ELK stack and an Flask REST server which is the interface
for job request.

## Prerequisites

In order to successfully execute the application, you should have:

 1. An account on [Nuvla](https://nuv.la).  Follow this
    [link](http://ssdocs.sixsq.com/en/latest/tutorials/ss/prerequisites.html#nuvla-account)
    where you'll find how to create the account.

 2. Cloud credentials added in your Nuvla user profile
    <div style="padding:14px"><img
    src="https://github.com/SixSq/SAR-app/blob/master/run/NuvlaProfile.png"
    width="75%"></div>

 3. Python `>=2.6 and <3` and python package manager `pip` installed. Usually
    can be installed with `sudo easy_install pip`.

 4. SlipStream python ss-client installed: `pip install slipstream-client`.

 ## Instructions

  1. Clone this repository with

     ```
     $ git clone https://github.com/SixSq/SAR-framework.git
     ```

  3. Set the environment variables

     ```
     $ export SLIPSTREAM_USERNAME=<nuv.la username>
     $ export SLIPSTREAM_PASSWORD=<nuv.la password>
     ```

     and run the SAR framework on [Nuvla](https://nuv.la) with

     ```
     $ ./SAR_server_run.sh
     ```
  4. Wait for the 'ready' state

  5. Recover the server's ip and start working with it !

    - Initialization with benchmarking specs and product:

    ```
    curl -H "Content-Type: application/json" -X POST http://<server_ip>/dmm/init -d
    '{
         "specs_vm": {
           "mapper": [4, 16000, 100],
           "reducer": [1, 1000, 100]
            },
         "product_list": [
           "S1A_IW_GRDH_1SDV_20151226T182813_20151226T182838_009217_00D48F_5D5F"
           ],
         "result": {
             "s3_credentials": [
                 "sos-ch-dk-2.exo.io",
                 "buket",
                 "xxx",
                 "yyy"
              ]
         }
     }'
      ```


    - Product generation with SLA:

    ```
    curl -H "Content-Type: application/json" -X POST http://<server_ip>/dmm/cli -d
     '{
       "SLA":{
         "requirements": [
                      <Time bound>,
                       <OFFER>], # still hardcoded to "CannedOffer_1"
          "product_list": [
                "S1A_IW_GRDH_1SDV_20151226T182813_20151226T182838_009217_00D48F_5D5F",
                "S1A_IW_GRDH_1SDV_20160424T182813_20160424T182838_010967_010769_AA98"
                ]
            },
        "result": {
                "s3_credentials":[
                      <host_base>,
                      <buket_id>,
                      <access_key>,
                      <secret_key>
                      ]
                    },
      }'
    ```
