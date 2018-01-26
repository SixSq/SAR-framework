#!/bin/bash

set -e
set -x

apt-get install -y \
    openjdk-8-jdk-headless \
    elasticsearch \
    kibana \
    logstash \
    ntp \
    nginx \
    apache2-utils \
    python-pip \
    git