#!/bin/bash

set -e
set -x

elk_repo() {
    apt-get update
    apt-get install -y apt-transport-https
    wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
    sudo echo "deb https://artifacts.elastic.co/packages/5.x/apt stable main" \
        /etc/apt/sources.list.d/elastic-5.x.list
}

ntp_conf() {
  timedatectl set-ntp no
}

elk_repo
ntp_conf
