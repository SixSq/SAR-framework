from __future__ import division
import sys
import math
from datetime import datetime
from collections import defaultdict

from elasticsearch import Elasticsearch
from slipstream_api import Api
from log import get_logger

logger = get_logger(name='summarizer')

api = Api()
server_host = 'localhost'
es = Elasticsearch([{'host': 'localhost', 'port': 9200}])

datetime_format = "%Y-%m-%dT%H:%M:%S"


def timestamp():
    return datetime.utcnow().strftime(datetime_format)


def _find_msg(msgs, mstr):
    """
    :param msgs: example: @MAPPER_RUN 2018-02-06T16:03:52 start deployment
    :param mstr: string to match
    :return: matched string
    """
    for m in msgs:
        if mstr in m:
            return m
    return ''


def _time_at(msgs, mstr):
    """
    :param msgs: example: @MAPPER_RUN 2018-02-06T16:03:52 start deployment
    :param mstr: string to match
    :return: datetime.datetime object
    """
    msg = _find_msg(msgs, mstr)
    if msg:
        time_str = msg.split(' ', 2)[1]
        return datetime.strptime(time_str, datetime_format)
    else:
        raise Exception('Failed to find %s in the list of messages to determine time.' % mstr)


def _total_time(dpl_state_times):
    total_time = dpl_state_times['Ready'] - _start_time(dpl_state_times)
    return total_time.seconds


def _start_time(dpl_state_times):
    return dpl_state_times['Created']


def _provisioning_time(dpl_state_times):
    return dpl_state_times['Executing'] - _start_time(dpl_state_times)


def _get_dpl_state_times(duid):
    events = api.get_deployment_events(duid)
    states_times = {}
    for e in events:
        states_times[e.content.get('state')] = \
            datetime.strptime(e.timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
    return states_times

def _intra_node_time(data, dpl_state_times):
    provisioning_time = _provisioning_time(dpl_state_times)

    install_time = _time_at(data, "start deployment") - \
                   dpl_state_times['Executing']

    processing_time = _time_at(data, 'finish processing') - \
                      _time_at(data, 'start processing')

    deployment_time = _time_at(data, 'finish deployment') - \
                      _time_at(data, 'start deployment')

    return {'provisioning': provisioning_time.seconds,
            'install': install_time.seconds,
            'deployment': deployment_time.seconds,
            'processing': processing_time.seconds,
            'intra-total': install_time.seconds + deployment_time.seconds}


def _compute_time_records(mappers_logs, reducer_logs, duid):
    """
    :param mappers_logs: list of lists with logs from each mapper
    :type mappers_logs: [[],]
    :param reducer_logs: list of logs from reducer
    :type reducer_logs: []
    :param duid: deployment id
    :return:
    """
    dpl_state_times = _get_dpl_state_times(duid)
    mappers_time = map(lambda x: _intra_node_time(x, dpl_state_times), mappers_logs)
    for i, v in enumerate(mappers_logs):
        mappers_time[i]['download'] = _download_time(v)

    reducer_time = _intra_node_time(reducer_logs, dpl_state_times)
    reducer_time['upload'] = _upload_time(reducer_logs)

    return {'mappers': mappers_time,
            'reducer': reducer_time,
            'total': _total_time(dpl_state_times)}


def _upload_time(data):
    upload_time = _time_at(data, 'finish uploading') - \
                  _time_at(data, 'start uploading')
    return upload_time.seconds


def _download_time(data):
    download_time = _time_at(data, 'finish downloading') - \
                    _time_at(data, 'start downloading')
    return download_time.seconds


def _get_service_offer(mapper, reducer):
    so_m = str(mapper[0]['_source']['fields']['service-offer'])
    so_r = str(reducer[0]['_source']['fields']['service-offer'])

    return [so_m, so_r]


def _get_products_list(log_entries_per_mapper):
    products = []
    for logs_list in log_entries_per_mapper:
        msg = _find_msg(logs_list, "finish downloading")
        msg_parts= msg.split(' -- ')
        if len(msg_parts) >= 2:
            prods = msg_parts[-1].split(' ')
            products += map(lambda x: x.strip(), prods)
    return products


def _service_offer(id):
    return api.cimi_get(id).json


def _get_specs(id):
    js = api.cimi_get(id).json
    return [js['resource:vcpu'], js['resource:ram'], js['resource:disk']]


def get_price(ids, time_records):
    mapper_multiplicity = len(time_records['mappers'])
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
        result = [h for h in hits['hits']
                  if h['_source']['fields'][field] == value]
    else:
        result = {}
    return result


def _div_node(run):
    mapper = _filter_field(run, "nodename", "mapper")
    reducer = _filter_field(run, "nodename", "reducer")

    return mapper, reducer


def _extract_node_data(mappers, reducer, duiid):
    l = []
    for m in mappers:
        l.append((m['_source']['host'], m['_source']['message']))

    mappers = defaultdict(list)
    for v, k in l:
        mappers[v].append(k)

    reducer = [r['_source']['message'] for r in reducer]

    return mappers, reducer


def _query_run(duid, cloud):
    query = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"fields.cloud": cloud}},
                    {"match": {"fields.duid": duid}}
                ]
            }
        }
    }

    return es.search(index='_all', body=query, size=300)


def _create_run_doc(cloud, offer, time_records, products, service_offers):
    run = {
        offer: {
            'components': {'mapper': _get_specs(service_offers[0]),
                           'reducer': _get_specs(service_offers[1])},
            'products': products,
            'price': '%.5f' % (get_price(service_offers, time_records)),
            'timestamp': timestamp(),
            'execution_time': time_records['total'],
            'time_records': {
                'mapper': time_records['mappers'],
                'reducer': time_records['reducer'],
                'total': time_records['total']}
        }
    }
    logger.info('Persisting run summary: %s' % run)

    rep = es.update(index='sar',
                    doc_type='eo-proc',
                    id=cloud,
                    body={"doc": run})


def summarize_run(duid, cloud, offer):
    logger.info("Running summarizer: %s, %s, %s" % (duid, cloud, offer))
    run = _query_run(duid, cloud)
    mappers, reducer = _div_node(run['hits'])
    logger.info('summarize_run mappers: %s' % mappers)
    logger.info('summarize_run reducer: %s' % reducer)
    mappers_data_dict, reducer_data = _extract_node_data(mappers, reducer, duid)
    logger.info('summarize_run mappers_data: %s' % mappers_data_dict)
    logger.info('summarize_run reducer_data: %s' % reducer_data)

    time_records = _compute_time_records(mappers_data_dict.values(), reducer_data, duid)
    products = _get_products_list(mappers_data_dict.values())
    service_offers = _get_service_offer(mappers, reducer)

    _create_run_doc(cloud, offer, time_records, products, service_offers)
    logger.info("Done summarizer: %s, %s, %s" % (duid, cloud, offer))


if __name__ == '__main__':
    duid, cloud, offer = sys.argv[1:4]
    summarize_run(duid, cloud, offer)
