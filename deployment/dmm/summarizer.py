from __future__ import division
import sys
import math
from datetime import datetime
from collections import defaultdict

from elasticsearch import Elasticsearch
from slipstream.api import Api
from log import get_logger

logger = get_logger(name='summarizer')

api = Api()
server_host = 'localhost'
res = Elasticsearch([{'host': 'localhost', 'port': 9200}])


def _extract_time(m):
    return (datetime.strptime(m, "%Y-%m-%d %H:%M:%S"))


def timestamp():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _time_at(msgs, str):
    msg = _find_msg(msgs, str)
    if len(msg.split(' - ')) > 1:
        time = msg.split(' - ')[1].strip()
    else:
        time = ''.join(msg.split(': ')[1].replace('T', ' '))[0:19]
    return (_extract_time(time))


def _total_time(reducer, duiid):
    start = _start_time(duiid)
    total_time = _time_at(reducer, "finish deployment") - start

    return total_time.seconds


def _start_time(duiid):
    temp = api.get_deployment(duiid)[3][0:19]

    return _extract_time(temp)


def _intra_node_time(data, duiid):
    start = _start_time(duiid)
    provisioning_time = _time_at(data, "currently in Provisioning") - start
    install_time = _time_at(data, "start deployment") - start

    deployment_time = _time_at(data, 'finish deployment') - \
                      _time_at(data, 'start deployment')

    processing_time = _time_at(data, 'finish processing') - \
                      _time_at(data, 'start processing')

    return ({'provisioning': provisioning_time.seconds,
             'install': install_time.seconds,
             'deployment': deployment_time.seconds,
             'processing': processing_time.seconds,
             'intra-total': (install_time.seconds +
                             deployment_time.seconds)})


def compute_time_records(mappers, reducer, duiid):
    mappers_time = map(lambda x: _intra_node_time(x, duiid),
                       mappers.values())
    for i, v in enumerate(mappers.values()):
        mappers_time[i]['download'] = _download_time(v)

    reducer_time = _intra_node_time(reducer, duiid)
    reducer_time['upload'] = _upload_time(reducer)

    return ({'mappers': mappers_time,
             'reducer': reducer_time,
             'total': _total_time(reducer, duiid)})


def _upload_time(data):
    upload_time = _time_at(data, 'finish upload') - \
                  _time_at(data, 'start upload')
    return upload_time


def _download_time(data):
    download_time = _time_at(data, 'finish downloading') - \
                    _time_at(data, 'start downloading')
    return download_time.seconds


def _find_msg(msgs, str):
    return (filter(lambda x: str in x, msgs)[0])


def _get_service_offer(mapper, reducer):
    so_m = str(mapper[0]['_source']['fields']['service-offer'])
    so_r = str(reducer[0]['_source']['fields']['service-offer'])

    return [so_m, so_r]


def get_product_info(data):
    raw_info = _find_msg(data, "finish downloading")
    info = raw_info.split(' - ')

    return (map(lambda x: x.strip(), info[3:5]))


def get_instance_type(id):
    _service_offer(0)['price:unitCost']


def _service_offer(id):
    return api.cimi_get(id).json


def _get_specs(id):
    js = api.cimi_get(id).json
    return [js['resource:vcpu'], js['resource:ram'], js['resource:disk']]


def get_price(ids, time_records):
    mapper_multiplicity = len(time_records['mapper'])
    time = time_records['total']
    try:
        mapper_unit_price = float(api.cimi_get(ids[0]).json['price:unitCost'])
        reducer_unit_price = float(api.cimi_get(ids[1]).json['price:unitCost'])
        logger.info("Mapper price:" + str(mapper_unit_price))
    except TypeError:
        logger.warn("No pricing available.")
        return 0

    if api.cimi_get(ids[0]).json['price:billingPeriodCode'] == 'HUR':
        time = math.ceil(float(time / 3600))
    else:
        time = float(time / 3600)
    cost = time * ((mapper_unit_price * mapper_multiplicity)
                   + reducer_unit_price)
    return cost


def _extract_field(data, field):
    return [v['_source'][field] for v in data.values()]


def _filter_field(hits, field, value):
    if hits['total'] > 0:
        hitsObj = hits['hits']
        result = [h for h in hitsObj \
                  if h['_source']['fields'][field] == value]
    else:
        result = {}
    return result


def div_node(run):
    mapper = _filter_field(run, "nodename", "mapper")
    reducer = _filter_field(run, "nodename", "reducer")

    return (mapper, reducer)


def extract_node_data(mapper, reducer, duiid):
    l = []
    for m in mapper:
        l.append((m['_source']['host'], m['_source']['message']))

    mappers = defaultdict(list)
    for v, k in l:
        mappers[v].append(k)

    reducer = [r['_source']['message'] for r in reducer]

    return (mappers, reducer)


def query_run(duiid, cloud):
    query = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"fields.cloud": cloud}},
                    {"match": {"fields.duiid": duiid}}
                ]
            }
        }
    }

    return res.search(index='_all', body=query, size=300)


def create_run_doc(cloud, offer, time_records, products, serviceOffers):
    run = {
        offer: {
            'components': {'mapper': _get_specs(serviceOffers[0]),
                           'reducer': _get_specs(serviceOffers[1])},
            'products': products,
            'price': '%.5f' % (get_price(serviceOffers, time_records)),
            'timestamp': timestamp(),
            'execution_time': time_records['total'],
            'time_records': {
                'mapper': time_records['mappers'],
                'reducer': time_records['reducer'],
                'total': time_records['total']}
        }
    }

    rep = res.update(index='sar',
                     doc_type='eo-proc',
                     id=cloud,
                     body={"doc": run})


def summarize_run(duiid, cloud, offer, ss_username, ss_password):
    api.login(ss_username, ss_password)
    response = query_run(duiid, cloud)
    [mappers, reducer] = div_node(response['hits'])
    [mappersData, reducerData] = extract_node_data(mappers, reducer, duiid)

    time_records = compute_time_records(mappersData, reducerData, duiid)
    products = map(lambda x: get_product_info(x), mappersData.values())
    serviceOffers = _get_service_offer(mappers, reducer)

    rep = create_run_doc(cloud, offer, time_records, products, serviceOffers)
    return rep


if __name__ == '__main__':
    [duiid, cloud, offer, ss_username, ss_password] = sys.argv[1:6]
    summarize_run(duiid, cloud, offer, ss_username, ss_password)
