from __future__ import division

import math

from elasticsearch import Elasticsearch
import server_dmm as srv_dmm
import summarizer as summ
from log import get_logger

logger = get_logger(name='dmm')

index = 'sar'
type = 'eo-proc'

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
    return map(int, spec)


def dmm(clouds, max_time, canned_offer_name):
    # TODO: if performance data is stored as SOs in SC on SS use api to get it.
    ranking = []
    for c in clouds:
        resp = query_db(c, max_time, canned_offer_name)
        if resp['_source']:
            cloud_canned_offer = resp['_source'][canned_offer_name]
            logger.info("%s: %s" % (canned_offer_name, cloud_canned_offer))
            total_time = cloud_canned_offer['execution_time']
            ratio = math.ceil(float(total_time / max_time))
            specs = cloud_canned_offer['components']
            specs['mapper'] = _prod_spec(ratio, specs['mapper'])
            logger.info("Spec: %s" % specs)
            specs = srv_dmm._format_specs(specs)
            # specs['mapper'] = math.ceil(ratio * float(specs['mapper'][0:3]))

            service_offers = srv_dmm._vm_service_offers(c, specs)
            cost = summ.get_price(service_offers, cloud_canned_offer['time_records'])
            ranking.append([c,
                            service_offers['mapper'],
                            service_offers['reducer'],
                            str(cost) + " EUR",
                            str(total_time) + " sec",
                            specs])
    return sorted(ranking, key=lambda x: x[3])


# if __name__ == '__main__':
#     cloud = ['ec2-eu-west']
#     time = 1000
#     offer = '1'
#     dmm(cloud, time, offer, ss_username, ss_password)
