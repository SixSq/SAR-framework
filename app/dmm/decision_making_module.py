from __future__ import division

import math

from elasticsearch import Elasticsearch
import server_dmm as srv_dmm
import summarizer as summ
from log import get_logger

logger = get_logger(name='dmm')

index = 'sar'
type = 'eo-proc'

es_client = Elasticsearch([{'host': 'localhost', 'port': 9200}])


def query_db(cloud, time_sec, offer):
    query = {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"_id": cloud}},
                    {"range": {"%s.execution_time" % offer: {"lte": time_sec}}}
                ]
            }
        }
    }
    return es_client.search(index=index, doc_type=type, body=query)


def _prod_spec(ratio, spec):
    logger.info('PROD SPEC: %s %s' % (ratio, spec))
    spec[0:2] = [math.ceil(float(c * ratio)) for c in spec[0:2]]
    return map(int, spec)


def dmm(clouds, max_time_sec, canned_offer_name):
    """Finds all benchmarks that are below max_time and returns the cheapest.

    :param clouds: list of clouds (we can deploy on)
    :param max_time: maximum compute time from SLA (in sec)
    :param canned_offer_name: canned offer name
    :return: cheapest found benchmark
    """
    # TODO: if performance data is stored as SOs in SC on SS use api to get it.
    ranking = []
    logger.info('Ranking services offers.')
    for cloud in clouds:
        resp = query_db(cloud, max_time_sec, canned_offer_name)
        if resp['hits']['total'] > 0:
            cloud_canned_offer = resp['hits']['hits'][0]['_source'][canned_offer_name]
            logger.info('Available benchmark data for canned offer %s: %s' %
                        (canned_offer_name, cloud_canned_offer))
            total_time = cloud_canned_offer['execution_time']
            ratio = math.ceil(float(total_time / max_time_sec))
            specs = cloud_canned_offer['components']
            specs['mapper'] = _prod_spec(ratio, specs['mapper'])
            logger.info("Spec: %s" % specs)
            specs = srv_dmm._format_specs(specs)
            # specs['mapper'] = math.ceil(ratio * float(specs['mapper'][0:3]))

            service_offers = srv_dmm._vm_service_offers(cloud, specs)
            cost = summ.get_price(service_offers, cloud_canned_offer['time_records'])
            ranking.append([cloud,
                            service_offers['mapper'],
                            service_offers['reducer'],
                            str(cost) + " EUR",
                            str(total_time) + " sec",
                            specs])
        else:
            logger.warn('No benchmark data for (cloud, max_time, offer) '
                        '%s, %s, %s ' % (cloud, max_time_sec, canned_offer_name))
    return sorted(ranking, key=lambda x: x[3])

# if __name__ == '__main__':
#     cloud = ['ec2-eu-west']
#     time = 1000
#     offer = '1'
#     dmm(cloud, time, offer, ss_username, ss_password)
