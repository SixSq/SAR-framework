#!/usr/bin/env bash

server=http://<server>


# POST /dmm/init
curl -H "Content-Type: application/json" -X POST $server/dmm/init -d '{
  "specs_vm":{
    "mapper":[4,16000,100],
    "reducer":[1,1000,50]
              },
  "result": {
      "s3_credentials":["sos.exo.io",
                        "eodata_output",
                        "key",
                        "secret"]
            },
"product_list": ["S1A_IW_GRDH_1SDV_20151226T182813_20151226T182838_009217_00D48F_5D5F",
                 "S1A_IW_GRDH_1SDV_20160424T182813_20160424T182838_010967_010769_AA98"],
"canned_offer": "CannedOffer_1"
}'

curl -H "Content-Type: application/json" -X POST $server/dmm/init -d '{
  "specs_vm":{
    "mapper":[4,16000,100],
    "reducer":[1,1000,50]
              },
  "result": {
      "s3_credentials":["sos.exo.io",
                        "eodata_output",
                        "key",
                        "secret"]
            },
"product_list": ["S1A_IW_GRDH_1SDV_20151226T182813_20151226T182838_009217_00D48F_5D5F",
                 "S1A_IW_GRDH_1SDV_20160424T182813_20160424T182838_010967_010769_AA98",
                 "S1A_IW_GRDH_1SDV_20160518T182817_20160518T182842_011317_011291_936E"],
"canned_offer": "CannedOffer_2"
}'


# POST /dmm/run
curl -H "Content-Type: application/json" -X POST $server/dmm/run -d '{
   "SLA": {
        "requirements": [1200, "CannedOffer_1"],
        "product_list": ["S1A_IW_GRDH_1SDV_20151226T182813_20151226T182838_009217_00D48F_5D5F",
                         "S1A_IW_GRDH_1SDV_20160424T182813_20160424T182838_010967_010769_AA98"]
          },
  "result": {
      "s3_credentials":["sos.exo.io",
                        "eodata_output",
                        "key",
                        "secret"]
            }
}'

# GET /dmm/cost
curl -H "Accept: application/json" $server/dmm/cost
