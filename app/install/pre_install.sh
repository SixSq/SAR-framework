#!/bin/bash

set -e
set -x

# Returns first global IPv4 address.
_get_ip() {
    ip addr | awk '/inet .*global/ { split($2, x, "/"); print x[1] }' | head -1
}

set_local_forward_resolution() {
    ip=$(_get_ip)
    echo "$ip $(hostname)" >> /etc/hosts
}

elk_repo() {
    apt-get update
    wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
    sudo echo "deb https://artifacts.elastic.co/packages/5.x/apt stable main" > \
        /etc/apt/sources.list.d/elastic-5.x.list
}

ntp_conf() {
  timedatectl set-ntp no
}

set_local_forward_resolution
elk_repo
ntp_conf
