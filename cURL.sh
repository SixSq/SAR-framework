#!/usr/bin/env bash

server=http://147.228.242.171:81

# POST /SLA_CLI
curl -H "Content-Type: application/json" -X POST $server/SLA_CLI -d '{
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


# POST /SLA_INIT

curl -H "Content-Type: application/json" -X POST $server/SLA_INIT -d '{
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
"product_list": ["S1A_IW_GRDH_1SDV_20151226T182813_20151226T182838_009217_00D48F_5D5F"]
}'


# GET /SLA_COST

curl -H "Accept: application/json" $server/SLA_COST
