#!/bin/bash
set -e
set -x

install_elk() {
    apt-get update
    apt-get install -y apt-transport-https
    wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -

    echo "deb https://artifacts.elastic.co/packages/5.x/apt stable main" | sudo tee -a /etc/apt/sources.list.d/elastic-5.x.list

    apt-get update

    apt-get install -y openjdk-8-jdk-headless
    apt-get install -y elasticsearch
    apt-get install -y kibana
    apt-get install -y logstash
}

install_ntp() {
  timedatectl set-ntp no
  apt-get install -y ntp
}

install_elk
install_ntp
