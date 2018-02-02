from __future__ import division

import math

from elasticsearch import Elasticsearch
import server_dmm as srv_dmm
import summarizer as summ
from log import get_logger

logger = get_logger(name='dmm')

index = 'sar'
type = 'eo-proc'

server_host = 'localhost'
res = Elasticsearch([{'host': 'localhost', 'port': 9200}])


# FIXME: use time in the query!
def query_db(cloud, time, offer):
    query = {"query": {
        "range": {
            "%s.execution_time" % offer: {
                "gte": 0,
            }
        }
    }
    }
    return res.get(index=index, doc_type=type, id=cloud)


''' decision making module

  : inputs    cloud, offer, time

  : query the document of according clouds for records with execution time equal
    or less than the input time
  : from th

'''


def _prod_spec(r, spec):
    spec[0:2] = [math.ceil(float(c * r)) for c in spec[0:2]]
    return (map(int, spec))


def dmm(cloud, time, offer, ssapi=None):
    # TODO: if performance data is stored as SOs in SC on SS use api to get it.
    ranking = []
    for c in cloud:
        resp = query_db(c, time, offer)
        if resp['_source']:
            logger.info("CannedOffer_1: %s" % resp['_source']['CannedOffer_1'])
            past_time = resp['_source'][offer]['time_records']
            ratio = math.ceil(float(past_time['total'] / time))
            specs = resp['_source'][offer]['components']
            specs['mapper'] = _prod_spec(ratio, specs['mapper'])
            logger.info("Spec: %s" % specs)
            specs = srv_dmm._format_specs(specs)
            # specs['mapper'] = math.ceil(ratio * float(specs['mapper'][0:3]))

            serviceOffers = srv_dmm._components_service_offers(c, specs)
            mapper_so = serviceOffers['mapper']
            reducer_so = serviceOffers['reducer']
            cost = summ.get_price([mapper_so, reducer_so], past_time)
            ranking.append([c,
                            mapper_so,
                            reducer_so,
                            str(cost) + " EUR",
                            str(past_time['total']) + " sec",
                            specs])
    return sorted(ranking, key=lambda x: x[3])


# if __name__ == '__main__':
#     cloud = ['ec2-eu-west']
#     time = 1000
#     offer = '1'
#     dmm(cloud, time, offer, ss_username, ss_password)
