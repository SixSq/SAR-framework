#!/bin/bash

set -e
set -x


cd /etc/elasticsearch/
cat >>elasticsearch.yml<<EOF
bootstrap.memory_lock: true
network.host: localhost
http.port: 9200
EOF

echo 'LimitMEMLOCK=infinity' >> /usr/lib/systemd/system/elasticsearch.service
echo 'MAX_LOCKED_MEMORY=unlimited' >> /etc/default/elasticsearch

systemctl daemon-reload
systemctl enable elasticsearch
systemctl start elasticsearch

#sleep 10
#exec 6<>/dev/tcp/127.0.0.1/9200 || echo "Elastic server is not listenining !"

#curl -XGET 'localhost:9200/_nodes?filter_path=**.mlockall&pretty'
#curl -XGET 'localhost:9200/?pretty'

#apt-get install -y kibana

cat >>/etc/kibana/kibana.yml<<EOF
server.port: 5601
server.host: "localhost"
elasticsearch.url: "http://localhost:9200"
EOF

systemctl enable kibana
systemctl start kibana

#sleep 10
#exec 6<>/dev/tcp/127.0.0.1/5601 || echo "Kibana service is not listenining !"

#apt-get install -y nginx apache2-utils

cd /etc/nginx/

cat >>sites-available/kibana<<EOF
server {
    listen 80;
    server_name elk-stack.co;

    location / {
        proxy_pass http://localhost:5601;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF


if [ -f /etc/nginx/sites-available/default ]; then
    mv /etc/nginx/sites-available/default /etc/nginx/sites-available/default.disabled
    ln -s /etc/nginx/sites-available/kibana /etc/nginx/sites-enabled/
fi


nginx -t
systemctl enable nginx
systemctl restart nginx

#sleep 5
#exec 6<>/dev/tcp/127.0.0.1/9200 || echo "Nginx server is not listenining !"

cd /etc/logstash/

cat >>conf.d/filebeat-input.conf<<EOF
input {
  beats {
    port => 5443
    type => syslog
  }
}
EOF

cat >>conf.d/syslog-filter.conf<<EOF
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

cat >>conf.d/output-elasticsearch.conf<<EOF
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

#sleep 10
#exec 6<>/dev/tcp/127.0.0.1/5443 || echo "Logstash service is not listenining !"


sudo rm -rf /var/lib/cloud/instance/sem/*
