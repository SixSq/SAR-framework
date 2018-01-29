#!/bin/bash

set -e
set -x

function abort() {
    echo "!!! Aborting: $@"
    exit 1
}

function _now_sec() {
    date +%s
}

function _wait_listens() {
    # host port [timeout seconds] [sleep interval seconds]
    wait_time=${3:-60}
    sleep_interval=${4:-2}
    stop_time=$(($(_now_sec) + $wait_time))
    while (( "$(_now_sec)" <= $stop_time )); do
        set +e
        res=$(ncat -v -4 $1 $2 < /dev/null 2>&1)
        if [ "$?" == "0" ]; then
            return 0
        else
            if ( ! (echo $res | grep -q "Connection refused") ); then
                abort "Failed to check $1:$2 with:" $res
            fi
        fi
        set -e
        sleep $sleep_interval
    done
    abort "Timed out after ${wait_time} sec waiting for $1:$2"
}

config_elasticsearch() {
    sed -i 's/^-Xms.*/-Xms256m/' /etc/elasticsearch/jvm.options
    sed -i 's/^-Xmx.*/-Xmx1g/' /etc/elasticsearch/jvm.options
    cat >>/etc/elasticsearch/elasticsearch.yml<<EOF
bootstrap.memory_lock: true
network.host: localhost
http.port: 9200
EOF

    echo 'LimitMEMLOCK=infinity' >> /usr/lib/systemd/system/elasticsearch.service
    echo 'MAX_LOCKED_MEMORY=unlimited' >> /etc/default/elasticsearch

    systemctl daemon-reload
    systemctl enable elasticsearch
    systemctl start elasticsearch
    _wait_listens 127.0.0.1 9200
    curl -XGET 'localhost:9200/?pretty'
}

config_kibana() {

    mkdir -p /var/log/kibana
    chown kibana /var/log/kibana

    cat >/etc/kibana/kibana.yml<<EOF
server.port: 5601
server.host: "localhost"
elasticsearch.url: "http://localhost:9200"
server.basePath: "/kibana"
logging.dest: /var/log/kibana/kibana.log
EOF

    systemctl enable kibana
    systemctl start kibana
    _wait_listens 127.0.0.1 5601
}

config_logstash() {
    cat >>/etc/logstash/conf.d/filebeat-input.conf<<EOF
input {
  beats {
    port => 5443
    type => syslog
  }
}
EOF

    cat >>/etc/logstash/conf.d/syslog-filter.conf<<EOF
filter {
  if [type] == "syslog" {
    grok {
      match => { "message" => "%{SYSLOGTIMESTAMP:syslog_timestamp} %{SYSLOGHOST:syslog_hostname} %{DATA:syslog_program}(?:\[%{POSINT:syslog_pid}\])?: %{GREEDYDATA:syslog_message}" }
      add_field => [ "received_at", "%{@timestamp}" ]
      add_field => [ "received_from", "%{host}" ]
    }
    date {
      match => [ "syslog_timestamp", "MMM  d HH:mm:ss", "MMM dd HH:mm:ss" ]
    }
  }
}
EOF

    cat >>/etc/logstash/conf.d/output-elasticsearch.conf<<EOF
output {
  elasticsearch { hosts => ["localhost:9200"]
    hosts => "localhost:9200"
    manage_template => false
    index => "%{[@metadata][beat]}-%{+YYYY.MM.dd}"
    document_type => "%{[@metadata][type]}"
  }
}
EOF

    systemctl enable logstash
    systemctl start logstash
    # FIXME: logstash resets the connection after binding of the ncat client.
    # _wait_listens 127.0.0.1 5443
}

config_nginx() {
    cat >/etc/nginx/sites-available/kibana<<'EOF'
server {
    listen 80;
    server_name dmm.eo;

    location /kibana/ {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;

        proxy_pass http://localhost:5601/;
        rewrite ^/kibana/(.*)$ /$1 break;
    }

    location /dmm/ {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;

        proxy_pass http://localhost:8080/;
    }
}
EOF
    ln -s /etc/nginx/sites-available/kibana /etc/nginx/sites-enabled/

    rm -f /etc/nginx/sites-enabled/default

    nginx -t
    systemctl enable nginx
    systemctl restart nginx
}

config_elasticsearch
config_logstash
config_kibana
config_nginx

sudo rm -rf /var/lib/cloud/instance/sem/*
